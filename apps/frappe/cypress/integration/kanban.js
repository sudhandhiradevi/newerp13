context('Kanban Board', () => {
	before(() => {
		cy.login();
		cy.visit('/app');
	});

	it('Create ToDo Kanban', () => {
		cy.visit('/app/todo');

		cy.get('.page-actions .custom-btn-group button').click();
		cy.get('.page-actions .custom-btn-group ul.dropdown-menu li').contains('Kanban').click();

		cy.focused().blur();
		cy.fill_field('board_name', 'ToDo Kanban', 'Data');
		cy.fill_field('field_name', 'Status', 'Select');
		cy.click_modal_primary_button('Save');

		cy.get('.title-text').should('contain', 'ToDo Kanban');
	});

	it('Create ToDo from kanban', () => {
		cy.intercept({
			method: 'POST',
			url: 'api/method/frappe.client.save'
		}).as('save-todo');

		cy.click_listview_primary_button('Add ToDo');

		cy.fill_field('description', 'Test Kanban ToDo', 'Text Editor');
		cy.get('.modal-footer .btn-primary').last().click();

		cy.wait('@save-todo');
	});

	it('Add and Remove fields', () => {
		cy.visit('/app/todo/view/kanban/ToDo Kanban');

		cy.intercept('POST', '/api/method/frappe.desk.doctype.kanban_board.kanban_board.save_settings').as('save-kanban');
		cy.intercept('POST', '/api/method/frappe.desk.doctype.kanban_board.kanban_board.update_order').as('update-order');

		cy.get('.page-actions .menu-btn-group > .btn').click();
		cy.get('.page-actions .menu-btn-group .dropdown-menu li').contains('Kanban Settings').click();
		cy.get('.add-new-fields').click();

		cy.get('.checkbox-options .checkbox').contains('ID').click();
		cy.get('.checkbox-options .checkbox').contains('Status').first().click();
		cy.get('.checkbox-options .checkbox').contains('Priority').click();

		cy.get('.modal-footer .btn-primary').last().click();

		cy.get('.frappe-control .label-area').contains('Show Labels').click();
		cy.click_modal_primary_button('Save');

		cy.wait('@save-kanban');

		cy.get('.kanban-column[data-column-value="Open"] .kanban-cards').as('open-cards');
		cy.get('@open-cards').find('.kanban-card .kanban-card-doc').first().should('contain', 'ID:');
		cy.get('@open-cards').find('.kanban-card .kanban-card-doc').first().should('contain', 'Status:');
		cy.get('@open-cards').find('.kanban-card .kanban-card-doc').first().should('contain', 'Priority:');

		cy.get('.page-actions .menu-btn-group > .btn').click();
		cy.get('.page-actions .menu-btn-group .dropdown-menu li').contains('Kanban Settings').click();
		cy.get_open_dialog().find('.frappe-control[data-fieldname="fields_html"] div[data-label="ID"] .remove-field').click();

		cy.wait('@update-order');
		cy.get_open_dialog().find('.frappe-control .label-area').contains('Show Labels').click();
		cy.get('.modal-footer .btn-primary').last().click();

		cy.wait('@save-kanban');

		cy.get('@open-cards').find('.kanban-card .kanban-card-doc').first().should('not.contain', 'ID:');

	});

	// it('Drag todo', () => {
	// 	cy.intercept({
	// 		method: 'POST',
	// 		url: 'api/method/frappe.desk.doctype.kanban_board.kanban_board.update_order_for_single_card'
	// 	}).as('drag-completed');

	// 	cy.get('.kanban-card-body')
	// 		.contains('Test Kanban ToDo').first()
	// 		.drag('[data-column-value="Closed"] .kanban-cards', { force: true });

	// cy.wait('@drag-completed');
	// });
});
