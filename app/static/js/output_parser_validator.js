class OutputParserValidator {
    static #patterns = {
        name: /^[a-zA-Z0-9_]+$/,
        field: /^[a-zA-Z0-9_]+$/
    };
    
    static validateName(name) {
        return this.#patterns.name.test(name);
    }
    
    static validateFields(fields) {
        return fields.every(field => 
            !field.value || this.#patterns.field.test(field.value)
        );
    }
    
    static validateForm() {
        const nameInput = document.querySelector('input[name="name"]');
        const fieldInputs = [...document.querySelectorAll('input[name="field_name"]')];
        
        const errors = [];
        
        if (!this.validateName(nameInput.value)) {
            errors.push('El nombre del parser solo puede contener letras, números y guiones bajos');
        }
        
        if (!this.validateFields(fieldInputs)) {
            errors.push('Los nombres de los campos solo pueden contener letras, números y guiones bajos');
        }
        
        if (errors.length) {
            alert(errors.join('\n'));
            return false;
        }
        
        return true;
    }
}

class OutputParserFieldManager {
    constructor(maxFields = 10) {
        this.maxFields = maxFields;
        this.fieldsTable = document.getElementById('fieldsTable').getElementsByTagName('tbody')[0];
        this.addFieldBtn = document.getElementById('addFieldBtn');
        this.initializeEventListeners();
    }
    
    initializeEventListeners() {
        this.addFieldBtn.addEventListener('click', () => this.addField());
        this.fieldsTable.addEventListener('click', (e) => this.handleDeleteField(e));
        this.updateAddButtonState();
    }
    
    addField() {
        if (this.fieldsTable.getElementsByTagName('tr').length >= this.maxFields) return;
        
        const newRow = this.createFieldRow();
        this.fieldsTable.appendChild(newRow);
        this.updateAddButtonState();
    }
    
    handleDeleteField(event) {
        if (event.target.closest('.deleteFieldBtn')) {
            event.target.closest('tr').remove();
            this.updateAddButtonState();
        }
    }
    
    updateAddButtonState() {
        this.addFieldBtn.disabled = 
            this.fieldsTable.getElementsByTagName('tr').length >= this.maxFields;
    }
    
    createFieldRow() {
        // Implementar la creación de la fila aquí
    }
} 