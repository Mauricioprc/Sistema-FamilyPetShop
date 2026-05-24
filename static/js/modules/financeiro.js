/**
 * modules/financeiro.js — Atualização das telas de resumo e revisão
 * Responsabilidade: preencher cards de resumo (passo 4) e ticket (passo 5).
 * Depende de: Formatter
 */

const Financeiro = (() => {

    /** Atualiza o card de resumo exibido no topo do passo 4. */
    function atualizarResumoPasso4(form) {
        const nomePet     = form.querySelector('#nome_pet')?.value || 'Pet';
        const tipoPet     = form.querySelector('input[name="tipo_pet"]:checked')?.value || 'Cão';
        const servico     = form.querySelector('input[name="nome_servico"]:checked')?.value || 'Não selecionado';
        const precoFinal  = form.querySelector('#preco_final')?.value || '0';

        _setText('resumo-nome-pet',    nomePet);
        _setText('resumo-nome-servico', servico);
        _setText('resumo-preco',       Formatter.currency(parseFloat(precoFinal)));

        const imgSrc = tipoPet === 'Gato'
            ? document.getElementById('mascote_cat_src')?.dataset.src
            : document.getElementById('mascote_dog_src')?.dataset.src;

        const iconeEl = document.getElementById('resumo-icone-pet');
        if (iconeEl && imgSrc) {
            iconeEl.innerHTML = `<img src="${imgSrc}" alt="${tipoPet}" style="height:50px;width:auto;object-fit:contain;" loading="lazy">`;
        }
    }

    /** Preenche o "ticket" de revisão no passo 5. */
    function atualizarRevisaoPasso5(form) {
        const nomeTutor = form.querySelector('#nome_tutor')?.value          || 'Não informado';
        const telefone  = form.querySelector('#telefone')?.value            || 'Não informado';
        const nomePet   = form.querySelector('#nome_pet')?.value            || 'Pet';
        const tipoPet   = form.querySelector('input[name="tipo_pet"]:checked')?.value  || '';
        const sexoPet   = form.querySelector('input[name="sexo_pet"]:checked')?.value  || '';
        const pesoPet   = form.querySelector('#peso_valor')?.value          || '0';
        const servico   = form.querySelector('input[name="nome_servico"]:checked')?.value || 'Não selecionado';
        const transporte= form.querySelector('input[name="transporte"]:checked')?.value  || '';
        const dataISO   = form.querySelector('#data')?.value                || '';
        const horario   = form.querySelector('#horario_preferido')?.value   || '';
        const precoEl   = document.getElementById('preco_calculado');

        const adicionais = Array.from(
            form.querySelectorAll('.minimal-optional-group input[type="checkbox"]:checked')
        ).map(cb => cb.value).join(' + ') || 'Nenhum adicional';

        _setText('review-nome-tutor',    nomeTutor);
        _setText('review-telefone',      telefone);
        _setText('review-nome-pet-full', nomePet);
        _setText('review-tipo-sexo',     `${tipoPet} (${sexoPet})`);
        _setText('review-peso',          `${pesoPet}kg`);
        _setText('review-servico-principal', servico);
        _setText('review-adicionais',    adicionais);
        _setText('review-transporte',    transporte);
        _setText('review-data-preferencial', `${Formatter.date(dataISO)} às ${horario}`);
        _setText('review-preco-total',   precoEl?.textContent || 'R$ 0,00');
    }

    function _setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    return { atualizarResumoPasso4, atualizarRevisaoPasso5 };

})();
