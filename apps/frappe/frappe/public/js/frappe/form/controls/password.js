frappe.ui.form.ControlPassword = class ControlPassword extends frappe.ui.form.ControlData {
	static input_type = "password";
	make() {
		super.make();
	}
	make_input() {
		var me = this;
		super.make_input();
		this.$input
			.parent()
			.append($('<span class="password-strength-indicator indicator"></span>'));
		this.$wrapper
			.find(".control-input-wrapper")
			.append($('<p class="password-strength-message text-muted small hidden"></p>'));

		this.indicator = this.$wrapper.find(".password-strength-indicator");
		this.message = this.$wrapper.find(".help-box");

		this.$input.on("keyup", () => {
			clearTimeout(this.check_password_timeout);
			this.check_password_timeout = setTimeout(() => {
				me.get_password_strength(me.$input.val());
			}, 500);
		});
	}
	get_password_strength(value) {
		var me = this;
		frappe.call({
			type: "POST",
			method: "frappe.core.doctype.user.user.test_password_strength",
			args: {
				new_password: value || "",
			},
			callback: function (r) {
				if (r.message && r.message.entropy) {
					var score = r.message.score,
						feedback = r.message.feedback;

					feedback.crack_time_display = r.message.crack_time_display;

					var indicators = ["grey", "red", "orange", "yellow", "green"];
					me.set_strength_indicator(indicators[score]);
				}
			},
		});
	}
	set_strength_indicator(color) {
		var message = __("Include symbols, numbers and capital letters in the password");
		this.indicator.removeClass().addClass("password-strength-indicator indicator " + color);
		this.message.html(message).removeClass("hidden");
	}
};
