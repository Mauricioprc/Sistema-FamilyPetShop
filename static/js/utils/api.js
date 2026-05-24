/**
 * utils/api.js — Requisições HTTP com CSRF automático
 * Responsabilidade única: comunicação com o backend Flask.
 */

const Api = (() => {

    function _getCsrf() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }

    /**
     * POST genérico com JSON.
     * @param {string} url
     * @param {object} body
     * @returns {Promise<Response>}
     */
    async function post(url, body = {}) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': _getCsrf()
            },
            body: JSON.stringify(body)
        });
    }

    /**
     * GET genérico.
     * @param {string} url
     * @returns {Promise<Response>}
     */
    async function get(url) {
        return fetch(url);
    }

    return { post, get };

})();
