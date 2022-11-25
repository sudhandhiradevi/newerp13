frappe.ui.form.ControlSelect = class ControlSelect extends frappe.ui.form.ControlData {
	static html_element = "select";
	make_input() {
		super.make_input();

		const is_xs_input = this.df.input_class && this.df.input_class.includes("input-xs");
		this.set_icon(is_xs_input);
		this.df.placeholder && this.set_placeholder(is_xs_input);

		this.$input.addClass("ellipsis");
		this.set_options();
	}
	set_icon(is_xs_input) {
		const select_icon_html = `<div class="select-icon ${is_xs_input ? "xs" : ""}">
				${frappe.utils.icon("select", is_xs_input ? "xs" : "sm")}
			</div>`;
		if (this.only_input) {
			this.$wrapper.append(select_icon_html);
		} else {
			this.$wrapper
				.find(".control-input")
				.addClass("flex align-center")
				.append(select_icon_html);
		}
	}
	set_placeholder(is_xs_input) {
		const placeholder_html = `<div class="placeholder ellipsis text-extra-muted ${
			is_xs_input ? "xs" : ""
		}">
				<span>${this.df.placeholder}</span>
			</div>`;
		if (this.only_input) {
			this.$wrapper.append(placeholder_html);
		} else {
			this.$wrapper.find(".control-input").append(placeholder_html);
		}
		this.toggle_placeholder();
		this.$input && this.$input.on("select-change", () => this.toggle_placeholder());
	}
	set_formatted_input(value) {
		// refresh options first - (new ones??)
		if (value == null) value = "";
		this.set_options(value);

		// set in the input element
		super.set_formatted_input(value);

		// check if the value to be set is selected
		var input_value = "";
		if (this.$input) {
			input_value = this.$input.val();
		}

		if (value && input_value && value !== input_value) {
			// trying to set a non-existant value
			// model value must be same as whatever the input is
			this.set_model_value(input_value);
		}
	}
	set_options(value) {
		// reset options, if something new is set
		var options = this.df.options || [];

		if (typeof this.df.options === "string") {
			options = this.df.options.split("\n");
		}

		// nothing changed
		if (JSON.stringify(options) === this.last_options) {
			return;
		}
		this.last_options = JSON.stringify(options);

		if (this.$input) {
			var selected = this.$input.find(":selected").val();
			this.$input.empty();
			frappe.ui.form.add_options(this.$input, options || []);

			if (value === undefined && selected) {
				this.$input.val(selected);
			}
		}
	}
	get_file_attachment_list() {
		if (!this.frm) return;
		var fl = frappe.model.docinfo[this.frm.doctype][this.frm.docname];
		if (fl && fl.attachments) {
			this.set_description("");
			var options = [""];
			$.each(fl.attachments, function (i, f) {
				options.push(f.file_url);
			});
			return options;
		} else {
			this.set_description(__("Please attach a file first."));
			return [""];
		}
	}
	toggle_placeholder() {
		const input_set = Boolean(this.$input.find("option:selected").text());
		this.$wrapper.find(".placeholder").toggle(!input_set);
	}
};

frappe.ui.form.add_options = function (input, options_list) {
	let $select = $(input);
	if (!Array.isArray(options_list)) {
		return $select;
	}
	// create options
	for (var i = 0, j = options_list.length; i < j; i++) {
		var v = options_list[i];
		var value = null;
		var label = null;
		if (!is_null(v)) {
			var is_value_null = is_null(v.value);
			var is_label_null = is_null(v.label);
			var is_disabled = Boolean(v.disabled);
			var is_selected = Boolean(v.selected);

			if (is_value_null && is_label_null) {
				value = v;
				label = __(v);
			} else {
				value = is_value_null ? "" : v.value;
				label = is_label_null ? __(value) : __(v.label);
			}
		}

		$("<option>")
			.html(cstr(label))
			.attr("value", value)
			.prop("disabled", is_disabled)
			.prop("selected", is_selected)
			.appendTo($select.get(0));
	}
	// select the first option
	$select.get(0).selectedIndex = 0;
	$select.trigger("select-change");
	return $select;
};

// add <option> list to <select>
(function ($) {
	$.fn.add_options = function (options_list) {
		return frappe.ui.form.add_options(this.get(0), options_list);
	};
	$.fn.set_working = function () {
		this.prop("disabled", true);
	};
	$.fn.done_working = function () {
		this.prop("disabled", false);
	};

	let original_val = $.fn.val;
	$.fn.val = function () {
		let result = original_val.apply(this, arguments);
		if (arguments.length > 0) $(this).trigger("select-change");
		return result;
	};
})(jQuery);
