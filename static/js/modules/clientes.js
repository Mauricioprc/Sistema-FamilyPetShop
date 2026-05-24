/**
 * modules/clientes.js — Lógica de transporte e endereço no wizard
 * Responsabilidade: mostrar/esconder campo de endereço conforme transporte.
 */

const Clientes = (() => {

    function init() {
        document.querySelectorAll('input[name="transporte"]')
            .forEach(r => r.addEventListener('change', _gerenciarTransporte));

        // Estado inicial (Táxi Dog pode já estar marcado por padrão em edição)
        _gerenciarTransporte();
    }

    function _gerenciarTransporte() {
        const taxiSelecionado   = document.getElementById('transporte_taxi')?.checked;
        const enderecoContainer = document.getElementById('endereco_container');
        const inputEndereco     = document.getElementById('endereco_busca');

        if (!enderecoContainer || !inputEndereco) return;

        if (taxiSelecionado) {
            enderecoContainer.classList.remove('d-none');
            inputEndereco.setAttribute('required', 'true');
        } else {
            enderecoContainer.classList.add('d-none');
            inputEndereco.removeAttribute('required');
            inputEndereco.value = '';
        }
    }

    return { init };

})();
