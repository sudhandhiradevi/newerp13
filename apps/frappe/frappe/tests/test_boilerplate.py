import ast
import copy
import glob
import os
import shutil
from io import StringIO
from unittest.mock import patch

import yaml

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.boilerplate import (
	_create_app_boilerplate,
	_get_user_inputs,
	github_workflow_template,
)


class TestBoilerPlate(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.default_hooks = frappe._dict(
			{
				"app_name": "test_app",
				"app_title": "Test App",
				"app_description": "This app's description contains 'single quotes' and \"double quotes\".",
				"app_publisher": "Test Publisher",
				"app_email": "example@example.org",
				"app_license": "MIT",
				"create_github_workflow": False,
			}
		)

		cls.default_user_input = frappe._dict(
			{
				"title": "Test App",
				"description": "This app's description contains 'single quotes' and \"double quotes\".",
				"publisher": "Test Publisher",
				"email": "example@example.org",
				"icon": "",  # empty -> default
				"color": "",
				"app_license": "MIT",
				"github_workflow": "n",
			}
		)

		cls.bench_path = frappe.utils.get_bench_path()
		cls.apps_dir = os.path.join(cls.bench_path, "apps")
		cls.gitignore_file = ".gitignore"
		cls.git_folder = ".git"

		cls.root_paths = [
			"requirements.txt",
			"README.md",
			"setup.py",
			"license.txt",
			cls.git_folder,
			cls.gitignore_file,
		]
		cls.paths_inside_app = [
			"__init__.py",
			"hooks.py",
			"patches.txt",
			"templates",
			"www",
			"config",
			"modules.txt",
			"public",
		]

	def create_app(self, hooks, no_git=False):
		self.addCleanup(self.delete_test_app, hooks.app_name)
		_create_app_boilerplate(self.apps_dir, hooks, no_git)

	@classmethod
	def delete_test_app(cls, app_name):
		test_app_dir = os.path.join(cls.bench_path, "apps", app_name)
		if os.path.exists(test_app_dir):
			shutil.rmtree(test_app_dir)

	@staticmethod
	def get_user_input_stream(inputs):
		user_inputs = []
		for value in inputs.values():
			if isinstance(value, list):
				user_inputs.extend(value)
			else:
				user_inputs.append(value)
		return StringIO("\n".join(user_inputs))

	def test_simple_input_to_boilerplate(self):
		with patch("sys.stdin", self.get_user_input_stream(self.default_user_input)):
			hooks = _get_user_inputs(self.default_hooks.app_name)
		self.assertDictEqual(hooks, self.default_hooks)

	def test_invalid_inputs(self):
		invalid_inputs = copy.copy(self.default_user_input).update(
			{
				"title": ["1nvalid Title", "valid title"],
			}
		)
		with patch("sys.stdin", self.get_user_input_stream(invalid_inputs)):
			hooks = _get_user_inputs(self.default_hooks.app_name)
		self.assertEqual(hooks.app_title, "valid title")

	def test_valid_ci_yaml(self):
		yaml.safe_load(github_workflow_template.format(**self.default_hooks))

	def test_create_app(self):
		app_name = "test_app"

		hooks = frappe._dict(
			{
				"app_name": app_name,
				"app_title": "Test App",
				"app_description": "This app's description contains 'single quotes' and \"double quotes\".",
				"app_publisher": "Test Publisher",
				"app_email": "example@example.org",
				"app_license": "MIT",
			}
		)

		self.create_app(hooks)
		new_app_dir = os.path.join(self.bench_path, self.apps_dir, app_name)

		paths = self.get_paths(new_app_dir, app_name)
		for path in paths:
			self.assertTrue(os.path.exists(path), msg=f"{path} should exist in {app_name} app")

		self.check_parsable_python_files(new_app_dir)

	def test_create_app_without_git_init(self):
		app_name = "test_app_no_git"

		hooks = frappe._dict(
			{
				"app_name": app_name,
				"app_title": "Test App",
				"app_description": "This app's description contains 'single quotes' and \"double quotes\".",
				"app_publisher": "Test Publisher",
				"app_email": "example@example.org",
				"app_license": "MIT",
			}
		)
		self.create_app(hooks, no_git=True)

		new_app_dir = os.path.join(self.apps_dir, app_name)

		paths = self.get_paths(new_app_dir, app_name)
		for path in paths:
			if os.path.basename(path) in (self.git_folder, self.gitignore_file):
				self.assertFalse(os.path.exists(path), msg=f"{path} shouldn't exist in {app_name} app")
			else:
				self.assertTrue(os.path.exists(path), msg=f"{path} should exist in {app_name} app")

		self.check_parsable_python_files(new_app_dir)

	def get_paths(self, app_dir, app_name):
		all_paths = list()

		for path in self.root_paths:
			all_paths.append(os.path.join(app_dir, path))

		all_paths.append(os.path.join(app_dir, app_name))

		for path in self.paths_inside_app:
			all_paths.append(os.path.join(app_dir, app_name, path))

		return all_paths

	def check_parsable_python_files(self, app_dir):
		# check if python files are parsable
		python_files = glob.glob(app_dir + "**/*.py", recursive=True)

		for python_file in python_files:
			with open(python_file) as p:
				try:
					ast.parse(p.read())
				except Exception as e:
					self.fail(f"Can't parse python file in new app: {python_file}\n" + str(e))
