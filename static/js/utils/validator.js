/**
 * utils/validator.js — Validação global de campos de formulário
 * Responsabilidade única: checar campos e retornar true/false.
 */

const Validator = (() => {

    /**
     * Valida todos os inputs[required], select[required] e textarea[required]
     * dentro de um elemento container (um passo do wizard, por ex.).
     * @param {HTMLElement} container
     * @returns {boolean}
     */
    function validateContainer(container) {
        if (!container) return true;

        // Limpa marcações anteriores
        container.querySelectorAll('.is-invalid, .is-valid')
            .forEach(el => el.classList.remove('is-invalid', 'is-valid'));

        let isValid = true;

        const inputs = container.querySelectorAll(
            'input[required], select[required], textarea[required]'
        );

        inputs.forEach(input => {
            // Validação extra: telefone com ao menos 10 dígitos
            if (input.id === 'telefone') {
                const digits = input.value.replace(/\D/g, '');
                input.setCustomValidity(digits.length < 10 ? 'Telefone incompleto' : '');
            } else {
                input.setCustomValidity('');
            }

            if (!input.checkValidity()) {
                input.classList.add('is-invalid');
                isValid = false;
            } else {
                input.classList.add('is-valid');
            }
        });

        return isValid;
    }

    /**
     * Remove marcações de validação de um container.
     * @param {HTMLElement} container
     */
    function clearValidation(container) {
        if (!container) return;
        container.querySelectorAll('.is-invalid, .is-valid')
            .forEach(el => el.classList.remove('is-invalid', 'is-valid'));
    }

    return { validateContainer, clearValidation };

})();
