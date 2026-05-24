/**
 * utils/formatter.js — Formatação de dados para exibição
 * Responsabilidade única: converter valores brutos em strings legíveis.
 */

const Formatter = (() => {

    /**
     * Formata um número como moeda BRL.
     * @param {number} value
     * @returns {string}  ex: "R$ 45,00"
     */
    function currency(value) {
        return Number(value).toLocaleString('pt-BR', {
            style: 'currency',
            currency: 'BRL'
        });
    }

    /**
     * Formata uma string de data ISO (YYYY-MM-DD) para pt-BR.
     * Evita o bug de fuso horário ao construir a data com partes individuais.
     * @param {string} isoDate  ex: "2026-04-15"
     * @returns {string}        ex: "15/04/2026"
     */
    function date(isoDate) {
        if (!isoDate) return '--/--/----';
        const [year, month, day] = isoDate.split('-');
        return new Date(year, month - 1, day).toLocaleDateString('pt-BR');
    }

    /**
     * Retorna uma string do tipo "15 de Abril de 2026".
     * @param {number} year
     * @param {number} month  (0-based)
     * @returns {string}
     */
    function monthYear(year, month) {
        const meses = [
            'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
            'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
        ];
        return `${meses[month]} de ${year}`;
    }

    return { currency, date, monthYear };

})();
