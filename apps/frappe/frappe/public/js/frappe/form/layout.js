import '../class';

frappe.ui.form.Layout = Class.extend({
	init: function (opts) {
		this.views = {};
		this.pages = [];
		this.sections = [];
		this.fields_list = [];
		this.fields_dict = {};

		$.extend(this, opts);
	},
	make: function() {
		if (!this.parent && this.body) {
			this.parent = this.body;
		}
		this.wrapper = $('<div class="form-layout">').appendTo(this.parent);
		this.message = $('<div class="form-message hidden"></div>').appendTo(this.wrapper);
		if (!this.fields) {
			this.fields = this.get_doctype_fields();
		}
		this.setup_tabbing();
		this.render();
	},
	show_empty_form_message: function() {
		if (!(this.wrapper.find(".frappe-control:visible").length || this.wrapper.find(".section-head.collapsed").length)) {
			this.show_message(__("This form does not have any input"));
		}
	},

	get_doctype_fields: function() {
		let fields = [
			this.get_new_name_field()
		];
		if (this.doctype_layout) {
			fields = fields.concat(this.get_fields_from_layout());
		} else {
			fields = fields.concat(frappe.meta.sort_docfields(frappe.meta.docfield_map[this.doctype]));
		}

		return fields;
	},

	get_new_name_field() {
		return {
			parent: this.frm.doctype,
			fieldtype: 'Data',
			fieldname: '__newname',
			reqd: 1,
			hidden: 1,
			label: __('Name'),
			get_status: function(field) {
				if (field.frm && field.frm.is_new()
					&& field.frm.meta.autoname
					&& ['prompt', 'name'].includes(field.frm.meta.autoname.toLowerCase())) {
					return 'Write';
				}
				return 'None';
			}
		};
	},

	get_fields_from_layout() {
		const fields = [];
		for (let f of this.doctype_layout.fields) {
			const docfield = copy_dict(frappe.meta.docfield_map[this.doctype][f.fieldname]);
			docfield.label = f.label;
			fields.push(docfield);
		}
		return fields;
	},

	show_message: function(html, color) {
		if (this.message_color) {
			// remove previous color
			this.message.removeClass(this.message_color);
		}
		this.message_color = (color && ['yellow', 'blue', 'red', 'green', 'orange'].includes(color)) ? color : 'blue';
		if (html) {
			if (html.substr(0, 1)!=='<') {
				// wrap in a block
				html = '<div>' + html + '</div>';
			}
			this.message.removeClass('hidden').addClass(this.message_color);
			$(html).appendTo(this.message);
		} else {
			this.message.empty().addClass('hidden');
		}
	},
	render: function (new_fields) {
		var me = this;
		var fields = new_fields || this.fields;

		this.section = null;
		this.column = null;

		if (this.with_dashboard) {
			this.setup_dashboard_section();
		}

		if (this.no_opening_section()) {
			this.make_section();
		}
		$.each(fields, function (i, df) {
			switch (df.fieldtype) {
				case "Fold":
					me.make_page(df);
					break;
				case "Section Break":
					me.make_section(df);
					break;
				case "Column Break":
					me.make_column(df);
					break;
				default:
					me.make_field(df);
			}
		});

	},

	no_opening_section: function () {
		return (this.fields[0] && this.fields[0].fieldtype != "Section Break") || !this.fields.length;
	},

	setup_dashboard_section: function () {
		if (this.no_opening_section()) {
			this.fields.unshift({fieldtype: 'Section Break'});
		}
	},

	replace_field: function (fieldname, df, render) {
		df.fieldname = fieldname; // change of fieldname is avoided
		if (this.fields_dict[fieldname] && this.fields_dict[fieldname].df) {
			const fieldobj = this.init_field(df, render);
			this.fields_dict[fieldname].$wrapper.remove();
			this.fields_list.splice(this.fields_dict[fieldname], 1, fieldobj);
			this.fields_dict[fieldname] = fieldobj;
			if (this.frm) {
				fieldobj.perm = this.frm.perm;
			}
			this.section.fields_list.splice(this.section.fields_dict[fieldname], 1, fieldobj);
			this.section.fields_dict[fieldname] = fieldobj;
			this.refresh_fields([df]);
		}
	},

	make_field: function (df, colspan, render) {
		!this.section && this.make_section();
		!this.column && this.make_column();

		const fieldobj = this.init_field(df, render);
		this.fields_list.push(fieldobj);
		this.fields_dict[df.fieldname] = fieldobj;
		if (this.frm) {
			fieldobj.perm = this.frm.perm;
		}

		this.section.fields_list.push(fieldobj);
		this.section.fields_dict[df.fieldname] = fieldobj;
		fieldobj.section = this.section;
	},

	init_field: function (df, render = false) {
		const fieldobj = frappe.ui.form.make_control({
			df: df,
			doctype: this.doctype,
			parent: this.column.wrapper.get(0),
			frm: this.frm,
			render_input: render,
			doc: this.doc,
			layout: this
		});

		fieldobj.layout = this;
		return fieldobj;
	},

	make_page: function (df) { // eslint-disable-line no-unused-vars
		var me = this,
			head = $('<div class="form-clickable-section text-center">\
				<a class="btn-fold h6 text-muted">' + __("Show more details") + '</a>\
			</div>').appendTo(this.wrapper);

		this.page = $('<div class="form-page second-page hide"></div>').appendTo(this.wrapper);

		this.fold_btn = head.find(".btn-fold").on("click", function () {
			var page = $(this).parent().next();
			if (page.hasClass("hide")) {
				$(this).removeClass("btn-fold").html(__("Hide details"));
				page.removeClass("hide");
				frappe.utils.scroll_to($(this), true, 30);
				me.folded = false;
			} else {
				$(this).addClass("btn-fold").html(__("Show more details"));
				page.addClass("hide");
				me.folded = true;
			}
		});

		this.section = null;
		this.folded = true;
	},

	unfold: function () {
		this.fold_btn.trigger('click');
	},

	make_section: function (df) {
		this.section = new frappe.ui.form.Section(this, df);

		// append to layout fields
		if (df) {
			this.fields_dict[df.fieldname] = this.section;
			this.fields_list.push(this.section);
		}

		this.column = null;
	},

	make_column: function (df) {
		this.column = new frappe.ui.form.Column(this.section, df);
		if (df && df.fieldname) {
			this.fields_list.push(this.column);
		}
	},

	refresh: function (doc) {
		var me = this;
		if (doc) this.doc = doc;

		if (this.frm) {
			this.wrapper.find(".empty-form-alert").remove();
		}

		// NOTE this might seem redundant at first, but it needs to be executed when frm.refresh_fields is called
		me.attach_doc_and_docfields(true);

		if (this.frm && this.frm.wrapper) {
			$(this.frm.wrapper).trigger("refresh-fields");
		}

		// dependent fields
		this.refresh_dependency();

		// refresh sections
		this.refresh_sections();

		if (this.frm) {
			// collapse sections
			this.refresh_section_collapse();
		}

		if (document.activeElement) {
			if (document.activeElement.tagName == 'INPUT' && this.is_numeric_field_active()) {
				document.activeElement.select();
			}
		}
	},

	is_numeric_field_active() {
		const control = $(document.activeElement).closest(".frappe-control");
		const fieldtype = (control.data() || {}).fieldtype;
		return frappe.model.numeric_fieldtypes.includes(fieldtype);
	},

	refresh_sections: function() {
		// hide invisible sections
		this.wrapper.find(".form-section:not(.hide-control)").each(function() {
			const section = $(this).removeClass("empty-section visible-section");
			if (section.find(".frappe-control:not(.hide-control)").length) {
				section.addClass("visible-section");
			} else {
				// nothing visible, hide the section
				section.addClass("empty-section");
			}
		});
	},

	refresh_fields: function (fields) {
		let fieldnames = fields.map((field) => {
			if (field.fieldname) return field.fieldname;
		});

		this.fields_list.map(fieldobj => {
			if (fieldnames.includes(fieldobj.df.fieldname)) {
				fieldobj.refresh();
				if (fieldobj.df["default"]) {
					fieldobj.set_input(fieldobj.df["default"]);
				}
			}
		});
	},

	add_fields: function (fields) {
		this.render(fields);
		this.refresh_fields(fields);
	},

	refresh_section_collapse: function () {
		if (!(this.sections && this.sections.length)) return;

		for (var i = 0; i < this.sections.length; i++) {
			var section = this.sections[i];
			var df = section.df;
			if (df && df.collapsible) {
				var collapse = true;

				if (df.collapsible_depends_on) {
					collapse = !this.evaluate_depends_on_value(df.collapsible_depends_on);
				}

				if (collapse && section.has_missing_mandatory()) {
					collapse = false;
				}

				section.collapse(collapse);
			}
		}
	},

	attach_doc_and_docfields: function (refresh) {
		var me = this;
		for (var i = 0, l = this.fields_list.length; i < l; i++) {
			var fieldobj = this.fields_list[i];
			if (me.doc) {
				fieldobj.doc = me.doc;
				fieldobj.doctype = me.doc.doctype;
				fieldobj.docname = me.doc.name;
				fieldobj.df = frappe.meta.get_docfield(me.doc.doctype,
					fieldobj.df.fieldname, me.doc.name) || fieldobj.df;

				// on form change, permissions can change
				if (me.frm) {
					fieldobj.perm = me.frm.perm;
				}
			}
			refresh && fieldobj.df && fieldobj.refresh && fieldobj.refresh();
		}
	},

	refresh_section_count: function () {
		this.wrapper.find(".section-count-label:visible").each(function (i) {
			$(this).html(i + 1);
		});
	},
	setup_tabbing: function () {
		var me = this;
		this.wrapper.on("keydown", function (ev) {
			if (ev.which == 9) {
				var current = $(ev.target),
					doctype = current.attr("data-doctype"),
					fieldname = current.attr("data-fieldname");
				if (doctype)
					return me.handle_tab(doctype, fieldname, ev.shiftKey);
			}
		});
	},
	handle_tab: function (doctype, fieldname, shift) {
		var me = this,
			grid_row = null,
			prev = null,
			fields = me.fields_list,
			in_grid = false,
			focused = false;

		// in grid
		if (doctype != me.doctype) {
			grid_row = me.get_open_grid_row();
			if (!grid_row || !grid_row.layout) {
				return;
			}
			fields = grid_row.layout.fields_list;
		}

		for (var i = 0, len = fields.length; i < len; i++) {
			if (fields[i].df.fieldname == fieldname) {
				if (shift) {
					if (prev) {
						this.set_focus(prev);
					} else {
						$(this.primary_button).focus();
					}
					break;
				}
				if (i < len - 1) {
					focused = me.focus_on_next_field(i, fields);
				}

				if (focused) {
					break;
				}
			}
			if (this.is_visible(fields[i]))
				prev = fields[i];
		}

		if (!focused) {
			// last field in this group
			if (grid_row) {
				// in grid
				if (grid_row.doc.idx == grid_row.grid.grid_rows.length) {
					// last row, close it and find next field
					grid_row.toggle_view(false, function () {
						grid_row.grid.frm.layout.handle_tab(grid_row.grid.df.parent, grid_row.grid.df.fieldname);
					});
				} else {
					// next row
					grid_row.grid.grid_rows[grid_row.doc.idx].toggle_view(true);
				}
			} else if (!shift) {
				// End of tab navigation
				$(this.primary_button).focus();
			}
		}

		return false;
	},
	focus_on_next_field: function (start_idx, fields) {
		// loop to find next eligible fields
		for (var i = start_idx + 1, len = fields.length; i < len; i++) {
			var field = fields[i];
			if (this.is_visible(field)) {
				if (field.df.fieldtype === "Table") {
					// open table grid
					if (!(field.grid.grid_rows && field.grid.grid_rows.length)) {
						// empty grid, add a new row
						field.grid.add_new_row();
					}
					// show grid row (if exists)
					field.grid.grid_rows[0].show_form();
					return true;

				} else if (!in_list(frappe.model.no_value_type, field.df.fieldtype)) {
					this.set_focus(field);
					return true;
				}
			}
		}
	},
	is_visible: function (field) {
		return field.disp_status === "Write" && (field.$wrapper && field.$wrapper.is(":visible"));
	},
	set_focus: function (field) {
		// next is table, show the table
		if (field.df.fieldtype=="Table") {
			if (!field.grid.grid_rows.length) {
				field.grid.add_new_row(1);
			} else {
				field.grid.grid_rows[0].toggle_view(true);
			}
		} else if (field.editor) {
			field.editor.set_focus();
		} else if (field.$input) {
			field.$input.focus();
		}
	},
	get_open_grid_row: function () {
		return $(".grid-row-open").data("grid_row");
	},
	refresh_dependency: function () {
		// Resolve "depends_on" and show / hide accordingly
		var me = this;

		// build dependants' dictionary
		var has_dep = false;

		for (var fkey in this.fields_list) {
			var f = this.fields_list[fkey];
			f.dependencies_clear = true;
			if (f.df.depends_on || f.df.mandatory_depends_on || f.df.read_only_depends_on) {
				has_dep = true;
			}
		}

		if (!has_dep) return;

		// show / hide based on values
		for (var i = me.fields_list.length - 1; i >= 0; i--) {
			var f = me.fields_list[i];
			f.guardian_has_value = true;
			if (f.df.depends_on) {
				// evaluate guardian

				f.guardian_has_value = this.evaluate_depends_on_value(f.df.depends_on);

				// show / hide
				if (f.guardian_has_value) {
					if (f.df.hidden_due_to_dependency) {
						f.df.hidden_due_to_dependency = false;
						f.refresh();
					}
				} else {
					if (!f.df.hidden_due_to_dependency) {
						f.df.hidden_due_to_dependency = true;
						f.refresh();
					}
				}
			}

			if (f.df.mandatory_depends_on) {
				this.set_dependant_property(f.df.mandatory_depends_on, f.df.fieldname, 'reqd');
			}

			if (f.df.read_only_depends_on) {
				this.set_dependant_property(f.df.read_only_depends_on, f.df.fieldname, 'read_only');
			}
		}

		this.refresh_section_count();
	},
	set_dependant_property: function (condition, fieldname, property) {
		let set_property = this.evaluate_depends_on_value(condition);
		let value = set_property ? 1 : 0;
		let form_obj;

		if (this.frm) {
			form_obj = this.frm;
		} else if (this.is_dialog || this.doctype === 'Web Form') {
			form_obj = this;
		}
		if (form_obj) {
			if (this.doc && this.doc.parent && this.doc.parentfield) {
				form_obj.setting_dependency = true;
				form_obj.set_df_property(this.doc.parentfield, property, value, this.doc.parent, fieldname, this.doc.name);
				form_obj.setting_dependency = false;
				// refresh child fields
				this.fields_dict[fieldname] && this.fields_dict[fieldname].refresh();
			} else {
				form_obj.set_df_property(fieldname, property, value);
			}
		}
	},
	evaluate_depends_on_value: function (expression) {
		var out = null;
		var doc = this.doc;

		if (!doc && this.get_values) {
			var doc = this.get_values(true);
		}

		if (!doc) {
			return;
		}

		var parent = this.frm ? this.frm.doc : this.doc || null;

		if (typeof (expression) === 'boolean') {
			out = expression;

		} else if (typeof (expression) === 'function') {
			out = expression(doc);

		} else if (expression.substr(0, 5)=='eval:') {
			try {
				out = frappe.utils.eval(expression.substr(5), { doc, parent });
				if (parent && parent.istable && expression.includes('is_submittable')) {
					out = true;
				}
			} catch (e) {
				frappe.throw(__('Invalid "depends_on" expression'));
			}

		} else if (expression.substr(0, 3)=='fn:' && this.frm) {
			out = this.frm.script_manager.trigger(expression.substr(3), this.doctype, this.docname);
		} else {
			var value = doc[expression];
			if ($.isArray(value)) {
				out = !!value.length;
			} else {
				out = !!value;
			}
		}

		return out;
	}
});

frappe.ui.form.Section = Class.extend({
	init: function(layout, df) {
		this.layout = layout;
		this.df = df || {};
		this.fields_list = [];
		this.fields_dict = {};

		this.make();
		// if (this.frm)
		// 	this.section.body.css({"padding":"0px 3%"})
		this.row = {
			wrapper: this.wrapper
		};

		this.refresh();
	},
	make: function() {
		if (!this.layout.page) {
			this.layout.page = $('<div class="form-page"></div>').appendTo(this.layout.wrapper);
		}
		let make_card = this.layout.card_layout;
		this.wrapper = $(`<div class="row form-section ${ make_card ? "card-section" : "" }">`)
			.appendTo(this.layout.page);
		this.layout.sections.push(this);

		if (this.df) {
			if (this.df.label) {
				this.make_head();
			}
			if (this.df.description) {
				$('<div class="col-sm-12 small text-muted form-section-description">' + __(this.df.description) + '</div>')
					.appendTo(this.wrapper);
			}
			if (this.df.cssClass) {
				this.wrapper.addClass(this.df.cssClass);
			}
			if (this.df.hide_border) {
				this.wrapper.toggleClass("hide-border", true);
			}
		}

		// for bc
		this.body = $('<div class="section-body">').appendTo(this.wrapper);
	},

	make_head: function () {
		this.head = $(`<div class="section-head">
			${__(this.df.label)}
			<span class="ml-2 collapse-indicator mb-1">
			</span>
		</div>`);
		this.head.appendTo(this.wrapper);
		this.indicator = this.head.find('.collapse-indicator');
		this.indicator.hide();
		if (this.df.collapsible) {
			// show / hide based on status
			this.collapse_link = this.head.on("click", () => {
				this.collapse();
			});

			this.indicator.show();
		}
	},
	refresh: function() {
		if (!this.df)
			return;

		// hide if explictly hidden
		var hide = this.df.hidden || this.df.hidden_due_to_dependency;

		// hide if no perm
		if (!hide && this.layout && this.layout.frm && !this.layout.frm.get_perm(this.df.permlevel || 0, "read")) {
			hide = true;
		}

		this.wrapper.toggleClass("hide-control", !!hide);
	},
	collapse: function (hide) {
		// unknown edge case
		if (!(this.head && this.body)) {
			return;
		}

		if (hide===undefined) {
			hide = !this.body.hasClass("hide");
		}

		this.body.toggleClass("hide", hide);
		this.head.toggleClass("collapsed", hide);

		let indicator_icon = hide ? 'down' : 'up-line';

		this.indicator & this.indicator.html(frappe.utils.icon(indicator_icon, 'sm', 'mb-1'));

		// refresh signature fields
		this.fields_list.forEach((f) => {
			if (f.df.fieldtype == 'Signature') {
				f.refresh();
			}
		});
	},

	is_collapsed() {
		return this.body.hasClass('hide');
	},

	has_missing_mandatory: function () {
		var missing_mandatory = false;
		for (var j = 0, l = this.fields_list.length; j < l; j++) {
			var section_df = this.fields_list[j].df;
			if (section_df.reqd && this.layout.doc[section_df.fieldname] == null) {
				missing_mandatory = true;
				break;
			}
		}
		return missing_mandatory;
	}
});

frappe.ui.form.Column = Class.extend({
	init: function(section, df) {
		if (!df) df = {};

		this.df = df;
		this.section = section;
		this.make();
		this.resize_all_columns();
	},
	make: function () {
		this.wrapper = $('<div class="form-column">\
			<form>\
			</form>\
		</div>').appendTo(this.section.body)
			.find("form")
			.on("submit", function () {
				return false;
			});

		if (this.df.label) {
			$('<label class="control-label">' + __(this.df.label)
				+ '</label>').appendTo(this.wrapper);
		}
	},
	resize_all_columns: function () {
		// distribute all columns equally
		var colspan = cint(12 / this.section.wrapper.find(".form-column").length);

		this.section.wrapper.find(".form-column").removeClass()
			.addClass("form-column")
			.addClass("col-sm-" + colspan);

	},
	refresh: function () {
		this.section.refresh();
	}
});
