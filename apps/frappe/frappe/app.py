# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import logging
import os

from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.local import LocalManager
from werkzeug.middleware.profiler import ProfilerMiddleware
from werkzeug.middleware.shared_data import SharedDataMiddleware
from werkzeug.wrappers import Request, Response

import frappe
import frappe.api
import frappe.auth
import frappe.handler
import frappe.monitor
import frappe.rate_limiter
import frappe.recorder
import frappe.utils.response
from frappe import _
from frappe.core.doctype.comment.comment import update_comments_in_parent_after_request
from frappe.middlewares import StaticDataMiddleware
from frappe.utils import cint, get_site_name, sanitize_html
from frappe.utils.error import make_error_snapshot
from frappe.website.serve import get_response

local_manager = LocalManager(frappe.local)

_site = None
_sites_path = os.environ.get("SITES_PATH", ".")
SAFE_HTTP_METHODS = ("GET", "HEAD", "OPTIONS")
UNSAFE_HTTP_METHODS = ("POST", "PUT", "DELETE", "PATCH")


class RequestContext:
	def __init__(self, environ):
		self.request = Request(environ)

	def __enter__(self):
		init_request(self.request)

	def __exit__(self, type, value, traceback):
		frappe.destroy()


@local_manager.middleware
@Request.application
def application(request: Request):
	response = None

	try:
		rollback = True

		init_request(request)

		frappe.recorder.record()
		frappe.monitor.start()
		frappe.rate_limiter.apply()
		frappe.api.validate_auth()

		if request.method == "OPTIONS":
			response = Response()

		elif frappe.form_dict.cmd:
			response = frappe.handler.handle()

		elif request.path.startswith("/api/"):
			response = frappe.api.handle()

		elif request.path.startswith("/backups"):
			response = frappe.utils.response.download_backup(request.path)

		elif request.path.startswith("/private/files/"):
			response = frappe.utils.response.download_private_file(request.path)

		elif request.method in ("GET", "HEAD", "POST"):
			response = get_response()

		else:
			raise NotFound

	except HTTPException as e:
		return e

	except Exception as e:
		response = handle_exception(e)

	else:
		rollback = after_request(rollback)

	finally:
		if request.method in ("POST", "PUT") and frappe.db and rollback:
			frappe.db.rollback()

		frappe.rate_limiter.update()
		frappe.monitor.stop(response)
		frappe.recorder.dump()

		log_request(request, response)
		process_response(response)
		frappe.destroy()

	return response


def init_request(request):
	frappe.local.request = request
	frappe.local.is_ajax = frappe.get_request_header("X-Requested-With") == "XMLHttpRequest"

	site = _site or request.headers.get("X-Frappe-Site-Name") or get_site_name(request.host)
	frappe.init(site=site, sites_path=_sites_path)

	if not (frappe.local.conf and frappe.local.conf.db_name):
		# site does not exist
		raise NotFound

	if frappe.local.conf.maintenance_mode:
		frappe.connect()
		if frappe.local.conf.allow_reads_during_maintenance:
			setup_read_only_mode()
		else:
			raise frappe.SessionStopped("Session Stopped")
	else:
		frappe.connect(set_admin_as_user=False)

	request.max_content_length = cint(frappe.local.conf.get("max_file_size")) or 10 * 1024 * 1024

	make_form_dict(request)

	if request.method != "OPTIONS":
		frappe.local.http_request = frappe.auth.HTTPRequest()


def setup_read_only_mode():
	"""During maintenance_mode reads to DB can still be performed to reduce downtime. This
	function sets up read only mode

	- Setting global flag so other pages, desk and database can know that we are in read only mode.
	- Setup read only database access either by:
	    - Connecting to read replica if one exists
	    - Or setting up read only SQL transactions.
	"""
	frappe.flags.read_only = True

	# If replica is available then just connect replica, else setup read only transaction.
	if frappe.conf.read_from_replica:
		frappe.connect_replica()
	else:
		frappe.db.begin(read_only=True)


def log_request(request, response):
	if hasattr(frappe.local, "conf") and frappe.local.conf.enable_frappe_logger:
		frappe.logger("frappe.web", allow_site=frappe.local.site).info(
			{
				"site": get_site_name(request.host),
				"remote_addr": getattr(request, "remote_addr", "NOTFOUND"),
				"base_url": getattr(request, "base_url", "NOTFOUND"),
				"full_path": getattr(request, "full_path", "NOTFOUND"),
				"method": getattr(request, "method", "NOTFOUND"),
				"scheme": getattr(request, "scheme", "NOTFOUND"),
				"http_status_code": getattr(response, "status_code", "NOTFOUND"),
			}
		)


def process_response(response):
	if not response:
		return

	# set cookies
	if hasattr(frappe.local, "cookie_manager"):
		frappe.local.cookie_manager.flush_cookies(response=response)

	# rate limiter headers
	if hasattr(frappe.local, "rate_limiter"):
		response.headers.extend(frappe.local.rate_limiter.headers())

	# CORS headers
	if hasattr(frappe.local, "conf"):
		set_cors_headers(response)


def set_cors_headers(response):
	if not (
		(allowed_origins := frappe.conf.allow_cors)
		and (request := frappe.local.request)
		and (origin := request.headers.get("Origin"))
	):
		return

	if allowed_origins != "*":
		if not isinstance(allowed_origins, list):
			allowed_origins = [allowed_origins]

		if origin not in allowed_origins:
			return

	cors_headers = {
		"Access-Control-Allow-Credentials": "true",
		"Access-Control-Allow-Origin": origin,
		"Vary": "Origin",
	}

	# only required for preflight requests
	if request.method == "OPTIONS":
		cors_headers["Access-Control-Allow-Methods"] = request.headers.get(
			"Access-Control-Request-Method"
		)

		if allowed_headers := request.headers.get("Access-Control-Request-Headers"):
			cors_headers["Access-Control-Allow-Headers"] = allowed_headers

		# allow browsers to cache preflight requests for upto a day
		if not frappe.conf.developer_mode:
			cors_headers["Access-Control-Max-Age"] = "86400"

	response.headers.extend(cors_headers)


def make_form_dict(request):
	import json

	request_data = request.get_data(as_text=True)
	if "application/json" in (request.content_type or "") and request_data:
		args = json.loads(request_data)
	else:
		args = {}
		args.update(request.args or {})
		args.update(request.form or {})

	if not isinstance(args, dict):
		frappe.throw(_("Invalid request arguments"))

	frappe.local.form_dict = frappe._dict(args)

	if "_" in frappe.local.form_dict:
		# _ is passed by $.ajax so that the request is not cached by the browser. So, remove _ from form_dict
		frappe.local.form_dict.pop("_")


def handle_exception(e):
	response = None
	http_status_code = getattr(e, "http_status_code", 500)
	return_as_message = False
	accept_header = frappe.get_request_header("Accept") or ""
	respond_as_json = (
		frappe.get_request_header("Accept")
		and (frappe.local.is_ajax or "application/json" in accept_header)
		or (frappe.local.request.path.startswith("/api/") and not accept_header.startswith("text"))
	)

	if not frappe.session.user:
		# If session creation fails then user won't be unset. This causes a lot of code that
		# assumes presence of this to fail. Session creation fails => guest or expired login
		# usually.
		frappe.session.user = "Guest"

	if respond_as_json:
		# handle ajax responses first
		# if the request is ajax, send back the trace or error message
		response = frappe.utils.response.report_error(http_status_code)

	elif isinstance(e, frappe.SessionStopped):
		response = frappe.utils.response.handle_session_stopped()

	elif (
		http_status_code == 500
		and (frappe.db and isinstance(e, frappe.db.InternalError))
		and (frappe.db and (frappe.db.is_deadlocked(e) or frappe.db.is_timedout(e)))
	):
		http_status_code = 508

	elif http_status_code == 401:
		frappe.respond_as_web_page(
			_("Session Expired"),
			_("Your session has expired, please login again to continue."),
			http_status_code=http_status_code,
			indicator_color="red",
		)
		return_as_message = True

	elif http_status_code == 403:
		frappe.respond_as_web_page(
			_("Not Permitted"),
			_("You do not have enough permissions to complete the action"),
			http_status_code=http_status_code,
			indicator_color="red",
		)
		return_as_message = True

	elif http_status_code == 404:
		frappe.respond_as_web_page(
			_("Not Found"),
			_("The resource you are looking for is not available"),
			http_status_code=http_status_code,
			indicator_color="red",
		)
		return_as_message = True

	elif http_status_code == 429:
		response = frappe.rate_limiter.respond()

	else:
		traceback = "<pre>" + sanitize_html(frappe.get_traceback()) + "</pre>"
		# disable traceback in production if flag is set
		if frappe.local.flags.disable_traceback and not frappe.local.dev_server:
			traceback = ""

		frappe.respond_as_web_page(
			"Server Error", traceback, http_status_code=http_status_code, indicator_color="red", width=640
		)
		return_as_message = True

	if e.__class__ == frappe.AuthenticationError:
		if hasattr(frappe.local, "login_manager"):
			frappe.local.login_manager.clear_cookies()

	if http_status_code >= 500:
		make_error_snapshot(e)

	if return_as_message:
		response = get_response("message", http_status_code=http_status_code)

	if frappe.conf.get("developer_mode") and not respond_as_json:
		# don't fail silently for non-json response errors
		print(frappe.get_traceback())

	return response


def after_request(rollback):
	# if HTTP method would change server state, commit if necessary
	if frappe.db and (
		frappe.local.flags.commit or frappe.local.request.method in UNSAFE_HTTP_METHODS
	):
		if frappe.db.transaction_writes:
			frappe.db.commit()
			rollback = False

	# update session
	if getattr(frappe.local, "session_obj", None):
		updated_in_db = frappe.local.session_obj.update()
		if updated_in_db:
			frappe.db.commit()
			rollback = False

	update_comments_in_parent_after_request()

	return rollback


def serve(
	port=8000, profile=False, no_reload=False, no_threading=False, site=None, sites_path="."
):
	global application, _site, _sites_path
	_site = site
	_sites_path = sites_path

	from werkzeug.serving import run_simple

	if profile or os.environ.get("USE_PROFILER"):
		application = ProfilerMiddleware(application, sort_by=("cumtime", "calls"))

	if not os.environ.get("NO_STATICS"):
		application = SharedDataMiddleware(
			application, {"/assets": str(os.path.join(sites_path, "assets"))}
		)

		application = StaticDataMiddleware(application, {"/files": str(os.path.abspath(sites_path))})

	application.debug = True
	application.config = {"SERVER_NAME": "localhost:8000"}

	log = logging.getLogger("werkzeug")
	log.propagate = False

	in_test_env = os.environ.get("CI")
	if in_test_env:
		log.setLevel(logging.ERROR)

	run_simple(
		"0.0.0.0",
		int(port),
		application,
		use_reloader=False if in_test_env else not no_reload,
		use_debugger=not in_test_env,
		use_evalex=not in_test_env,
		threaded=not no_threading,
	)
