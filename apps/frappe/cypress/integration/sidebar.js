const verify_attachment_visibility = (document, is_private) => {
	cy.visit(`/app/${document}`);

	const assertion = is_private ? "be.checked" : "not.be.checked";
	cy.findByRole("button", { name: "Attach File" }).click();

	cy.get_open_dialog()
		.find(".file-upload-area")
		.selectFile("cypress/fixtures/sample_image.jpg", {
			action: "drag-drop",
		});

	cy.get_open_dialog().findByRole("checkbox", { name: "Private" }).should(assertion);
};

context("Sidebar", () => {
	before(() => {
		cy.visit("/login");
		cy.login();

		return cy
			.window()
			.its("frappe")
			.then((frappe) => {
				return frappe.call("frappe.tests.ui_test_helpers.create_blog_post");
			});
	});

	it("Verify attachment visibility config", () => {
		verify_attachment_visibility("doctype/Blog Post", true);
		verify_attachment_visibility("blog-post/test-blog-attachment-post", false);
	});

	it('Test for checking "Assigned To" counter value, adding filter and adding & removing an assignment', () => {
		cy.visit("/app/doctype");
		cy.click_sidebar_button("Assigned To");

		//To check if no filter is available in "Assigned To" dropdown
		cy.get(".empty-state").should("contain", "No filters found");

		//Assigning a doctype to a user
		cy.visit("/app/doctype/ToDo");
		cy.get(".form-assignments > .flex > .text-muted").click();
		cy.get_field("assign_to_me", "Check").click();
		cy.get(".modal-footer > .standard-actions > .btn-primary").click();
		cy.visit("/app/doctype");
		cy.click_sidebar_button("Assigned To");

		//To check if filter is added in "Assigned To" dropdown after assignment
		cy.get(".group-by-field.show > .dropdown-menu > .group-by-item > .dropdown-item").should(
			"contain",
			"1"
		);

		//To check if there is no filter added to the listview
		cy.get(".filter-selector > .btn").should("contain", "Filter");

		//To add a filter to display data into the listview
		cy.get(".group-by-field.show > .dropdown-menu > .group-by-item > .dropdown-item").click();

		//To check if filter is applied
		cy.click_filter_button().should("contain", "1 filter");
		cy.get(".fieldname-select-area > .awesomplete > .form-control").should(
			"have.value",
			"Assigned To"
		);
		cy.get(".condition").should("have.value", "like");
		cy.get(".filter-field > .form-group > .input-with-feedback").should(
			"have.value",
			`%${cy.config("testUser")}%`
		);
		cy.click_filter_button();

		//To remove the applied filter
		cy.clear_filters();

		//To remove the assignment
		cy.visit("/app/doctype/ToDo");
		cy.get(".assignments > .avatar-group > .avatar > .avatar-frame").click();
		cy.get(".remove-btn").click({ force: true });
		cy.hide_dialog();
		cy.visit("/app/doctype");
		cy.click_sidebar_button("Assigned To");
		cy.get(".empty-state").should("contain", "No filters found");
	});
});
