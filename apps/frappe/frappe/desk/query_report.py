# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import unicode_literals

import json
import os
from datetime import timedelta

from six import iteritems, string_types

import frappe
import frappe.desk.reportview
from frappe import _
from frappe.core.utils import ljust_list
from frappe.model.utils import render_include
from frappe.modules import get_module_path, scrub
from frappe.permissions import get_role_permissions
from frappe.utils import (
	cint,
	cstr,
	flt,
	format_duration,
	get_html_format,
	get_url_to_form,
	gzip_decompress,
)


def get_report_doc(report_name):
	doc = frappe.get_doc("Report", report_name)
	doc.custom_columns = []

	if doc.report_type == "Custom Report":
		custom_report_doc = doc
		reference_report = custom_report_doc.reference_report
		doc = frappe.get_doc("Report", reference_report)
		doc.custom_report = report_name
		if custom_report_doc.json:
			data = json.loads(custom_report_doc.json)
			if data:
				doc.custom_columns = data["columns"]
		doc.is_custom_report = True

	if not doc.is_permitted():
		frappe.throw(
			_("You don't have access to Report: {0}").format(report_name),
			frappe.PermissionError,
		)

	if not frappe.has_permission(doc.ref_doctype, "report"):
		frappe.throw(
			_("You don't have permission to get a report on: {0}").format(doc.ref_doctype),
			frappe.PermissionError,
		)

	if doc.disabled:
		frappe.throw(_("Report {0} is disabled").format(report_name))

	return doc


def get_report_result(report, filters):
	res = None

	if report.report_type == "Query Report":
		res = report.execute_query_report(filters)

	elif report.report_type == "Script Report":
		res = report.execute_script_report(filters)

	elif report.report_type == "Custom Report":
		ref_report = get_report_doc(report.report_name)
		res = get_report_result(ref_report, filters)

	return res


@frappe.read_only()
def generate_report_result(
	report, filters=None, user=None, custom_columns=None, is_tree=False, parent_field=None
):
	user = user or frappe.session.user
	filters = filters or []

	if filters and isinstance(filters, string_types):
		filters = json.loads(filters)

	res = get_report_result(report, filters) or []

	columns, result, message, chart, report_summary, skip_total_row = ljust_list(res, 6)
	columns = [get_column_as_dict(col) for col in (columns or [])]
	report_column_names = [col["fieldname"] for col in columns]

	# convert to list of dicts
	result = normalize_result(result, columns)

	if report.custom_columns:
		# saved columns (with custom columns / with different column order)
		columns = report.custom_columns

	# unsaved custom_columns
	if custom_columns:
		for custom_column in custom_columns:
			columns.insert(custom_column["insert_after_index"] + 1, custom_column)

	# all columns which are not in original report
	report_custom_columns = [
		column for column in columns if column["fieldname"] not in report_column_names
	]

	if report_custom_columns:
		result = add_custom_column_data(report_custom_columns, result)

	if result:
		result = get_filtered_data(report.ref_doctype, columns, result, user)

	if cint(report.add_total_row) and result and not skip_total_row:
		result = add_total_row(result, columns, is_tree=is_tree, parent_field=parent_field)

	return {
		"result": result,
		"columns": columns,
		"message": message,
		"chart": chart,
		"report_summary": report_summary,
		"skip_total_row": skip_total_row or 0,
		"status": None,
		"execution_time": frappe.cache().hget("report_execution_time", report.name) or 0,
	}


def normalize_result(result, columns):
	# Converts to list of dicts from list of lists/tuples
	data = []
	column_names = [column["fieldname"] for column in columns]
	if result and isinstance(result[0], (list, tuple)):
		for row in result:
			row_obj = {}
			for idx, column_name in enumerate(column_names):
				row_obj[column_name] = row[idx]
			data.append(row_obj)
	else:
		data = result

	return data


@frappe.whitelist()
def background_enqueue_run(report_name, filters=None, user=None):
	"""run reports in background"""
	if not user:
		user = frappe.session.user
	report = get_report_doc(report_name)
	track_instance = frappe.get_doc(
		{
			"doctype": "Prepared Report",
			"report_name": report_name,
			# This looks like an insanity but, without this it'd be very hard to find Prepared Reports matching given condition
			# We're ensuring that spacing is consistent. e.g. JS seems to put no spaces after ":", Python on the other hand does.
			"filters": json.dumps(json.loads(filters)),
			"ref_report_doctype": report_name,
			"report_type": report.report_type,
			"query": report.query,
			"module": report.module,
		}
	)
	track_instance.insert(ignore_permissions=True)
	frappe.db.commit()
	track_instance.enqueue_report()

	return {
		"name": track_instance.name,
		"redirect_url": get_url_to_form("Prepared Report", track_instance.name),
	}


@frappe.whitelist()
def get_script(report_name):
	report = get_report_doc(report_name)
	module = report.module or frappe.db.get_value("DocType", report.ref_doctype, "module")

	is_custom_module = frappe.get_cached_value("Module Def", module, "custom")

	# custom modules are virtual modules those exists in DB but not in disk.
	module_path = "" if is_custom_module else get_module_path(module)
	report_folder = module_path and os.path.join(module_path, "report", scrub(report.name))
	script_path = report_folder and os.path.join(report_folder, scrub(report.name) + ".js")
	print_path = report_folder and os.path.join(report_folder, scrub(report.name) + ".html")

	script = None
	if os.path.exists(script_path):
		with open(script_path, "r") as f:
			script = f.read()
			script += f"\n\n//# sourceURL={scrub(report.name)}.js"

	html_format = get_html_format(print_path)

	if not script and report.javascript:
		script = report.javascript
		script += f"\n\n//# sourceURL={scrub(report.name)}__custom"

	if not script:
		script = "frappe.query_reports['%s']={}" % report_name

	return {
		"script": render_include(script),
		"html_format": html_format,
		"execution_time": frappe.cache().hget("report_execution_time", report_name) or 0,
	}


@frappe.whitelist()
@frappe.read_only()
def run(
	report_name,
	filters=None,
	user=None,
	ignore_prepared_report=False,
	custom_columns=None,
	is_tree=False,
	parent_field=None,
):
	report = get_report_doc(report_name)
	if not user:
		user = frappe.session.user
	if not frappe.has_permission(report.ref_doctype, "report"):
		frappe.msgprint(
			_("Must have report permission to access this report."),
			raise_exception=True,
		)

	result = None

	if (
		report.prepared_report
		and not report.disable_prepared_report
		and not ignore_prepared_report
		and not custom_columns
	):
		if filters:
			if isinstance(filters, string_types):
				filters = json.loads(filters)

			dn = filters.get("prepared_report_name")
			filters.pop("prepared_report_name", None)
		else:
			dn = ""
		result = get_prepared_report_result(report, filters, dn, user)
	else:
		result = generate_report_result(report, filters, user, custom_columns, is_tree, parent_field)

	result["add_total_row"] = report.add_total_row and not result.get("skip_total_row", False)

	return result


def add_custom_column_data(custom_columns, result):
	custom_column_data = get_data_for_custom_report(custom_columns)

	for column in custom_columns:
		key = (column.get("doctype"), column.get("fieldname"))
		if key in custom_column_data:
			for row in result:
				row_reference = row.get(column.get("link_field"))
				# possible if the row is empty
				if not row_reference:
					continue
				row[column.get("fieldname")] = custom_column_data.get(key).get(row_reference)

	return result


def get_prepared_report_result(report, filters, dn="", user=None):
	latest_report_data = {}
	doc = None
	if dn:
		# Get specified dn
		doc = frappe.get_doc("Prepared Report", dn)
	else:
		# Only look for completed prepared reports with given filters.
		doc_list = frappe.get_all(
			"Prepared Report",
			filters={
				"status": "Completed",
				"filters": json.dumps(filters),
				"owner": user,
				"report_name": report.get("custom_report") or report.get("report_name"),
			},
			order_by="creation desc",
		)

		if doc_list:
			# Get latest
			doc = frappe.get_doc("Prepared Report", doc_list[0])

	if doc:
		try:
			# Prepared Report data is stored in a GZip compressed JSON file
			attached_file_name = frappe.db.get_value(
				"File",
				{"attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
				"name",
			)
			attached_file = frappe.get_doc("File", attached_file_name)
			compressed_content = attached_file.get_content()
			uncompressed_content = gzip_decompress(compressed_content)
			data = json.loads(uncompressed_content.decode("utf-8"))
			if data:
				columns = json.loads(doc.columns) if doc.columns else data[0]

				for column in columns:
					if isinstance(column, dict) and column.get("label"):
						column["label"] = _(column["label"])

				latest_report_data = {"columns": columns, "result": data}
		except Exception:
			frappe.log_error(frappe.get_traceback())
			frappe.delete_doc("Prepared Report", doc.name)
			frappe.db.commit()
			doc = None

	latest_report_data.update({"prepared_report": True, "doc": doc})

	return latest_report_data


@frappe.whitelist()
def export_query():
	"""export from query reports"""
	data = frappe._dict(frappe.local.form_dict)
	data.pop("cmd", None)
	data.pop("csrf_token", None)

	if isinstance(data.get("filters"), string_types):
		filters = json.loads(data["filters"])

	if data.get("report_name"):
		report_name = data["report_name"]
		frappe.permissions.can_export(
			frappe.get_cached_value("Report", report_name, "ref_doctype"),
			raise_exception=True,
		)

	file_format_type = data.get("file_format_type")
	custom_columns = frappe.parse_json(data.get("custom_columns", "[]"))
	include_indentation = data.get("include_indentation")
	visible_idx = data.get("visible_idx")

	if isinstance(visible_idx, string_types):
		visible_idx = json.loads(visible_idx)

	if file_format_type == "Excel":
		data = run(report_name, filters, custom_columns=custom_columns)
		data = frappe._dict(data)
		if not data.columns:
			frappe.respond_as_web_page(
				_("No data to export"),
				_("You can try changing the filters of your report."),
			)
			return

		columns = get_columns_dict(data.columns)

		from frappe.utils.xlsxutils import make_xlsx

		data["result"] = handle_duration_fieldtype_values(data.get("result"), data.get("columns"))
		xlsx_data, column_widths = build_xlsx_data(columns, data, visible_idx, include_indentation)
		xlsx_file = make_xlsx(xlsx_data, "Query Report", column_widths=column_widths)

		frappe.response["filename"] = report_name + ".xlsx"
		frappe.response["filecontent"] = xlsx_file.getvalue()
		frappe.response["type"] = "binary"


def handle_duration_fieldtype_values(result, columns):
	for i, col in enumerate(columns):
		fieldtype = None
		if isinstance(col, string_types):
			col = col.split(":")
			if len(col) > 1:
				if col[1]:
					fieldtype = col[1]
					if "/" in fieldtype:
						fieldtype, options = fieldtype.split("/")
				else:
					fieldtype = "Data"
		else:
			fieldtype = col.get("fieldtype")

		if fieldtype == "Duration":
			for entry in range(0, len(result)):
				row = result[entry]
				if isinstance(row, dict):
					val_in_seconds = row[col.fieldname]
					if val_in_seconds:
						duration_val = format_duration(val_in_seconds)
						row[col.fieldname] = duration_val
				else:
					val_in_seconds = row[i]
					if val_in_seconds:
						duration_val = format_duration(val_in_seconds)
						row[i] = duration_val

	return result


def build_xlsx_data(columns, data, visible_idx, include_indentation, ignore_visible_idx=False):
	result = [[]]
	column_widths = []

	for column in data.columns:
		if column.get("hidden"):
			continue
		result[0].append(column.get("label"))
		column_width = cint(column.get("width", 0))
		# to convert into scale accepted by openpyxl
		column_width /= 10
		column_widths.append(column_width)

	# build table from result
	for row_idx, row in enumerate(data.result):
		# only pick up rows that are visible in the report
		if ignore_visible_idx or row_idx in visible_idx:
			row_data = []
			if isinstance(row, dict):
				for col_idx, column in enumerate(data.columns):
					if column.get("hidden"):
						continue
					label = column.get("label")
					fieldname = column.get("fieldname")
					cell_value = row.get(fieldname, row.get(label, ""))
					if cint(include_indentation) and "indent" in row and col_idx == 0:
						cell_value = ("    " * cint(row["indent"])) + cstr(cell_value)
					row_data.append(cell_value)
			elif row:
				row_data = row

			result.append(row_data)

	return result, column_widths


def add_total_row(result, columns, meta=None, is_tree=False, parent_field=None):
	total_row = [""] * len(columns)
	has_percent = []

	for i, col in enumerate(columns):
		fieldtype, options, fieldname = None, None, None
		if isinstance(col, string_types):
			if meta:
				# get fieldtype from the meta
				field = meta.get_field(col)
				if field:
					fieldtype = meta.get_field(col).fieldtype
					fieldname = meta.get_field(col).fieldname
			else:
				col = col.split(":")
				if len(col) > 1:
					if col[1]:
						fieldtype = col[1]
						if "/" in fieldtype:
							fieldtype, options = fieldtype.split("/")
					else:
						fieldtype = "Data"
		else:
			fieldtype = col.get("fieldtype")
			fieldname = col.get("fieldname")
			options = col.get("options")

		for row in result:
			if i >= len(row):
				continue
			cell = row.get(fieldname) if isinstance(row, dict) else row[i]
			if fieldtype in ["Currency", "Int", "Float", "Percent", "Duration"] and flt(cell):
				if not (is_tree and row.get(parent_field)):
					total_row[i] = flt(total_row[i]) + flt(cell)

			if fieldtype == "Percent" and i not in has_percent:
				has_percent.append(i)

			if fieldtype == "Time" and cell:
				if not total_row[i]:
					total_row[i] = timedelta(hours=0, minutes=0, seconds=0)
				total_row[i] = total_row[i] + cell

		if fieldtype == "Link" and options == "Currency":
			total_row[i] = result[0].get(fieldname) if isinstance(result[0], dict) else result[0][i]

	for i in has_percent:
		total_row[i] = flt(total_row[i]) / len(result)

	first_col_fieldtype = None
	if isinstance(columns[0], string_types):
		first_col = columns[0].split(":")
		if len(first_col) > 1:
			first_col_fieldtype = first_col[1].split("/")[0]
	else:
		first_col_fieldtype = columns[0].get("fieldtype")

	if first_col_fieldtype not in ["Currency", "Int", "Float", "Percent", "Date"]:
		total_row[0] = _("Total")

	result.append(total_row)
	return result


@frappe.whitelist()
def get_data_for_custom_field(doctype, fieldname, field=None):

	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not Permitted"), frappe.PermissionError)

	if field:
		custom_field = field + " as " + fieldname
	else:
		custom_field = fieldname

	value_map = frappe._dict(frappe.get_all(doctype, fields=["name", custom_field], as_list=1))

	return value_map


def get_data_for_custom_report(columns):
	doc_field_value_map = {}

	for column in columns:
		if column.get("link_field"):
			fieldname = column.get("fieldname")
			doctype = column.get("doctype")
			field = column.get("field")
			doc_field_value_map[(doctype, fieldname)] = get_data_for_custom_field(doctype, fieldname, field)

	return doc_field_value_map


@frappe.whitelist()
def save_report(reference_report, report_name, columns):
	report_doc = get_report_doc(reference_report)

	docname = frappe.db.exists(
		"Report",
		{
			"report_name": report_name,
			"is_standard": "No",
			"report_type": "Custom Report",
		},
	)

	if docname:
		report = frappe.get_doc("Report", docname)
		existing_jd = json.loads(report.json)
		existing_jd["columns"] = json.loads(columns)
		report.update({"json": json.dumps(existing_jd, separators=(",", ":"))})
		report.save()
		frappe.msgprint(_("Report updated successfully"))

		return docname
	else:
		new_report = frappe.get_doc(
			{
				"doctype": "Report",
				"report_name": report_name,
				"json": f'{{"columns":{columns}}}',
				"ref_doctype": report_doc.ref_doctype,
				"is_standard": "No",
				"report_type": "Custom Report",
				"reference_report": reference_report,
			}
		).insert(ignore_permissions=True)
		frappe.msgprint(_("{0} saved successfully").format(new_report.name))
		return new_report.name


def get_filtered_data(ref_doctype, columns, data, user):
	result = []
	linked_doctypes = get_linked_doctypes(columns, data)
	match_filters_per_doctype = get_user_match_filters(linked_doctypes, user=user)
	shared = frappe.share.get_shared(ref_doctype, user)
	columns_dict = get_columns_dict(columns)

	role_permissions = get_role_permissions(frappe.get_meta(ref_doctype), user)
	if_owner = role_permissions.get("if_owner", {}).get("report")

	if match_filters_per_doctype:
		for row in data:
			# Why linked_doctypes.get(ref_doctype)? because if column is empty, linked_doctypes[ref_doctype] is removed
			if linked_doctypes.get(ref_doctype) and shared and row[linked_doctypes[ref_doctype]] in shared:
				result.append(row)

			elif has_match(
				row,
				linked_doctypes,
				match_filters_per_doctype,
				ref_doctype,
				if_owner,
				columns_dict,
				user,
			):
				result.append(row)
	else:
		result = list(data)

	return result


def has_match(
	row,
	linked_doctypes,
	doctype_match_filters,
	ref_doctype,
	if_owner,
	columns_dict,
	user,
):
	"""Returns True if after evaluating permissions for each linked doctype
	- There is an owner match for the ref_doctype
	- `and` There is a user permission match for all linked doctypes

	Returns True if the row is empty

	Note:
	Each doctype could have multiple conflicting user permission doctypes.
	Hence even if one of the sets allows a match, it is true.
	This behavior is equivalent to the trickling of user permissions of linked doctypes to the ref doctype.
	"""
	resultant_match = True

	if not row:
		# allow empty rows :)
		return resultant_match

	for doctype, filter_list in doctype_match_filters.items():
		matched_for_doctype = False

		if doctype == ref_doctype and if_owner:
			idx = linked_doctypes.get("User")
			if idx is not None and row[idx] == user and columns_dict[idx] == columns_dict.get("owner"):
				# owner match is true
				matched_for_doctype = True

		if not matched_for_doctype:
			for match_filters in filter_list:
				match = True
				for dt, idx in linked_doctypes.items():
					# case handled above
					if dt == "User" and columns_dict[idx] == columns_dict.get("owner"):
						continue

					cell_value = None
					if isinstance(row, dict):
						cell_value = row.get(idx)
					elif isinstance(row, (list, tuple)):
						cell_value = row[idx]

					if (
						dt in match_filters
						and cell_value not in match_filters.get(dt)
						and frappe.db.exists(dt, cell_value)
					):
						match = False
						break

				# each doctype could have multiple conflicting user permission doctypes, hence using OR
				# so that even if one of the sets allows a match, it is true
				matched_for_doctype = matched_for_doctype or match

				if matched_for_doctype:
					break

		# each doctype's user permissions should match the row! hence using AND
		resultant_match = resultant_match and matched_for_doctype

		if not resultant_match:
			break

	return resultant_match


def get_linked_doctypes(columns, data):
	linked_doctypes = {}

	columns_dict = get_columns_dict(columns)

	for idx, col in enumerate(columns):
		df = columns_dict[idx]
		if df.get("fieldtype") == "Link":
			if data and isinstance(data[0], (list, tuple)):
				linked_doctypes[df["options"]] = idx
			else:
				# dict
				linked_doctypes[df["options"]] = df["fieldname"]

	# remove doctype if column is empty
	columns_with_value = []
	for row in data:
		if row:
			if len(row) != len(columns_with_value):
				if isinstance(row, (list, tuple)):
					row = enumerate(row)
				elif isinstance(row, dict):
					row = row.items()

				for col, val in row:
					if val and col not in columns_with_value:
						columns_with_value.append(col)

	items = list(iteritems(linked_doctypes))

	for doctype, key in items:
		if key not in columns_with_value:
			del linked_doctypes[doctype]

	return linked_doctypes


def get_columns_dict(columns):
	"""Returns a dict with column docfield values as dict
	The keys for the dict are both idx and fieldname,
	so either index or fieldname can be used to search for a column's docfield properties
	"""
	columns_dict = frappe._dict()
	for idx, col in enumerate(columns):
		col_dict = get_column_as_dict(col)
		columns_dict[idx] = col_dict
		columns_dict[col_dict["fieldname"]] = col_dict

	return columns_dict


def get_column_as_dict(col):
	col_dict = frappe._dict()

	# string
	if isinstance(col, string_types):
		col = col.split(":")
		if len(col) > 1:
			if "/" in col[1]:
				col_dict["fieldtype"], col_dict["options"] = col[1].split("/")
			else:
				col_dict["fieldtype"] = col[1]
			if len(col) == 3:
				col_dict["width"] = col[2]

		col_dict["label"] = col[0]
		col_dict["fieldname"] = frappe.scrub(col[0])

	# dict
	else:
		col_dict.update(col)
		if "fieldname" not in col_dict:
			col_dict["fieldname"] = frappe.scrub(col_dict["label"])

	return col_dict


def get_user_match_filters(doctypes, user):
	match_filters = {}

	for dt in doctypes:
		filter_list = frappe.desk.reportview.build_match_conditions(dt, user, False)
		if filter_list:
			match_filters[dt] = filter_list

	return match_filters
