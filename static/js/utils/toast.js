/**
 * utils/toast.js — Alertas temporários para respostas AJAX
 * Responsabilidade única: mostrar feedback visual sem reload de página.
 */

function mostrarAjaxAlert(categoria, mensagem) {
    const container = document.getElementById('ajax-alerts');
    if (!container) {
        alert(mensagem);
        return;
    }

    const classes = {
        success: 'alert-orange-custom',
        danger: 'alert-danger-custom',
        warning: 'alert-warning alert-warning-custom',
        info: 'alert-info'
    };
    const cls = classes[categoria] || classes.info;

    const el = document.createElement('div');
    el.className = `alert ${cls} alert-dismissible fade show`;
    el.setAttribute('role', 'alert');
    el.innerHTML = `${mensagem}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Fechar"></button>`;
    container.appendChild(el);

    setTimeout(() => {
        el.classList.remove('show');
        el.addEventListener('transitionend', () => el.remove());
        setTimeout(() => el.remove(), 500);
    }, 5000);
}
