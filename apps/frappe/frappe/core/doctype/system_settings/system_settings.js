frappe.ui.form.on("System Settings", {
	refresh: function(frm) {
		frappe.call({
			method: "frappe.core.doctype.system_settings.system_settings.load",
			callback: function(data) {
				frappe.all_timezones = data.message.timezones;
				frm.set_df_property("time_zone", "options", frappe.all_timezones);

				$.each(data.message.defaults, function(key, val) {
					frm.set_value(key, val, null, true);
					frappe.sys_defaults[key] = val;
				});
				if (frm.re_setup_moment) {
					frappe.app.setup_moment();
					delete frm.re_setup_moment;
				}
			}
		});
	},
	enable_password_policy: function(frm) {
		if (frm.doc.enable_password_policy == 0) {
			frm.set_value("minimum_password_score", "");
		} else {
			frm.set_value("minimum_password_score", "2");
		}
	},
	enable_two_factor_auth: function(frm) {
		if (frm.doc.enable_two_factor_auth == 0) {
			frm.set_value("bypass_2fa_for_retricted_ip_users", 0);
			frm.set_value("bypass_restrict_ip_check_if_2fa_enabled", 0);
		}
	},
	enable_prepared_report_auto_deletion: function(frm) {
		if (frm.doc.enable_prepared_report_auto_deletion) {
			if (!frm.doc.prepared_report_expiry_period) {
				frm.set_value('prepared_report_expiry_period', 7);
			}
		}
	},
	on_update: function(frm) {
		if (frappe.boot.time_zone && frappe.boot.time_zone.system !== frm.doc.time_zone) {
			// Clear cache after saving to refresh the values of boot.
			frappe.ui.toolbar.clear_cache();
		}
	},
	first_day_of_the_week(frm) {
		frm.re_setup_moment = true;
	},
});
