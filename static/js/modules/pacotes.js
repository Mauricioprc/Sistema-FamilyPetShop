/**
 * modules/pacotes.js — Cálculo de preço dinâmico do wizard de agendamento
 * Responsabilidade: calcular e exibir o preço estimado.
 * Depende de: Formatter
 */

const Pacotes = (() => {

    // Tabela de acréscimos por faixa de peso (em kg)
    const PRECO_POR_PESO = [
        { max: 5,   adicional: 0.00  },
        { max: 10,  adicional: 10.00 },
        { max: 25,  adicional: 25.00 },
        { max: 40,  adicional: 40.00 },
        { max: 999, adicional: 60.00 }
    ];

    let _pesoRange, _pesoValor, _servicoSelector, _precoFinalInput, _precoDisplay;

    /**
     * Inicializa o módulo.
     * @param {object} refs - referências aos elementos DOM relevantes
     */
    function init(refs) {
        _pesoRange       = refs.pesoRange;
        _pesoValor       = refs.pesoValor;
        _servicoSelector = refs.servicoSelector;
        _precoFinalInput = refs.precoFinalInput;
        _precoDisplay    = refs.precoDisplay;

        // Sincroniza range ↔ input numérico
        if (_pesoRange && _pesoValor) {
            _pesoRange.addEventListener('input', () => {
                _pesoValor.value = _pesoRange.value;
                calcular();
            });
            _pesoValor.addEventListener('input', () => {
                let v = parseInt(_pesoValor.value, 10);
                if (isNaN(v) || v < 1)  v = 1;
                if (v > 50)             v = 50;
                _pesoValor.value = v;
                _pesoRange.value = v;
                calcular();
            });
            // Valor inicial
            _pesoValor.value = _pesoRange.value || 10;
        }

        // Serviço principal
        if (_servicoSelector) {
            _servicoSelector.addEventListener('change', calcular);
        }

        // Adicionais (checkboxes)
        document.querySelectorAll('.minimal-optional-group input[type="checkbox"]')
            .forEach(cb => cb.addEventListener('change', calcular));

        // Transporte
        document.querySelectorAll('input[name="transporte"]')
            .forEach(r => r.addEventListener('change', calcular));

        calcular();
    }

    /** Calcula e exibe o preço total estimado. */
    function calcular() {
        if (!_pesoRange || !_servicoSelector) return;

        const peso    = parseFloat(_pesoRange.value || 0);
        const servico = _servicoSelector.querySelector('input[name="nome_servico"]:checked');

        if (!servico) {
            _atualizar(0);
            return;
        }

        const precoBase = parseFloat(servico.getAttribute('data-base-price') || 0);

        // Adicional por peso
        let adicionalPeso = 0;
        for (const regra of PRECO_POR_PESO) {
            if (peso <= regra.max) { adicionalPeso = regra.adicional; break; }
        }

        // Adicionais selecionados
        let adicionalServicos = 0;
        document.querySelectorAll('.minimal-optional-group input[type="checkbox"]:checked')
            .forEach(cb => {
                adicionalServicos += parseFloat(cb.getAttribute('data-adicional-price') || 0);
            });

        // Táxi Dog
        const taxiDog = document.getElementById('transporte_taxi');
        const adicionalTaxi = (taxiDog?.checked)
            ? parseFloat(taxiDog.getAttribute('data-taxi-price') || 0)
            : 0;

        _atualizar(precoBase + adicionalPeso + adicionalServicos + adicionalTaxi);
    }

    function _atualizar(total) {
        const formatado = Formatter.currency(total);
        if (_precoDisplay)    _precoDisplay.textContent = formatado;
        if (_precoFinalInput) _precoFinalInput.value    = total.toFixed(2);
    }

    return { init, calcular };

})();
