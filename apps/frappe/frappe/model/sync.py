# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

from __future__ import print_function, unicode_literals

"""
	Sync's doctype and docfields from txt files to database
	perms will get synced only if none exist
"""
import os

import frappe
from frappe.modules.import_file import import_file_by_path
from frappe.modules.patch_handler import block_user
from frappe.utils import update_progress_bar


def sync_all(force=0, verbose=False, reset_permissions=False):
	block_user(True)

	for app in frappe.get_installed_apps():
		sync_for(app, force, verbose=verbose, reset_permissions=reset_permissions)

	block_user(False)

	frappe.clear_cache()


def sync_for(app_name, force=0, sync_everything=False, verbose=False, reset_permissions=False):
	files = []

	if app_name == "frappe":
		# these need to go first at time of install
		for d in (
			("core", "docfield"),
			("core", "docperm"),
			("core", "doctype_action"),
			("core", "doctype_link"),
			("core", "role"),
			("core", "has_role"),
			("core", "doctype"),
			("core", "user"),
			("custom", "custom_field"),
			("custom", "property_setter"),
			("website", "web_form"),
			("website", "web_template"),
			("website", "web_form_field"),
			("website", "portal_menu_item"),
			("data_migration", "data_migration_mapping_detail"),
			("data_migration", "data_migration_mapping"),
			("data_migration", "data_migration_plan_mapping"),
			("data_migration", "data_migration_plan"),
			("desk", "number_card"),
			("desk", "dashboard_chart"),
			("desk", "dashboard"),
			("desk", "onboarding_permission"),
			("desk", "onboarding_step"),
			("desk", "onboarding_step_map"),
			("desk", "module_onboarding"),
			("desk", "workspace_link"),
			("desk", "workspace_chart"),
			("desk", "workspace_shortcut"),
			("desk", "workspace"),
		):
			files.append(os.path.join(frappe.get_app_path("frappe"), d[0], "doctype", d[1], d[1] + ".json"))

	for module_name in frappe.local.app_modules.get(app_name) or []:
		folder = os.path.dirname(frappe.get_module(app_name + "." + module_name).__file__)
		files = get_doc_files(files, folder)

	l = len(files)

	if l:
		for i, doc_path in enumerate(files):
			import_file_by_path(
				doc_path, force=force, ignore_version=True, reset_permissions=reset_permissions
			)

			frappe.db.commit()

			# show progress bar
			update_progress_bar("Updating DocTypes for {0}".format(app_name), i, l)

		# print each progress bar on new line
		print()


def get_doc_files(files, start_path):
	"""walk and sync all doctypes and pages"""

	if not files:
		files = []

	# load in sequence - warning for devs
	document_types = [
		"doctype",
		"page",
		"report",
		"dashboard_chart_source",
		"print_format",
		"website_theme",
		"web_form",
		"web_template",
		"notification",
		"print_style",
		"data_migration_mapping",
		"data_migration_plan",
		"workspace",
		"onboarding_step",
		"module_onboarding",
	]

	for doctype in document_types:
		doctype_path = os.path.join(start_path, doctype)
		if os.path.exists(doctype_path):
			for docname in os.listdir(doctype_path):
				if os.path.isdir(os.path.join(doctype_path, docname)):
					doc_path = os.path.join(doctype_path, docname, docname) + ".json"
					if os.path.exists(doc_path):
						if not doc_path in files:
							files.append(doc_path)

	return files
