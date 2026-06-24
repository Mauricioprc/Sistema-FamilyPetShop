/**
 * backup-reminder.js — Aviso para o usuário fazer backup do banco de dados
 * a cada 7 dias. Ao clicar em "Sim", baixa o arquivo .db automaticamente.
 */

document.addEventListener('DOMContentLoaded', () => {
    fetch('/backup/status')
        .then(resp => resp.ok ? resp.json() : null)
        .then(dados => {
            if (dados && dados.precisa_backup) {
                mostrarModalBackup();
            }
        })
        .catch(err => console.error('Erro ao verificar status do backup:', err));
});

function mostrarModalBackup() {
    // Evita duplicar o modal se a função for chamada mais de uma vez
    if (document.getElementById('modalBackup')) return;

    const modalHtml = `
        <div class="modal fade" id="modalBackup" tabindex="-1" aria-hidden="true">
          <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
              <div class="modal-header">
                <h5 class="modal-title"><i class="bi bi-cloud-arrow-down-fill"></i> Hora do backup!</h5>
              </div>
              <div class="modal-body">
                <p>Já faz <strong>7 dias ou mais</strong> desde o último backup do sistema.</p>
                <p>Deseja baixar agora uma cópia do banco de dados para o seu computador?</p>
              </div>
              <div class="modal-footer">
                <button type="button" class="btn btn-outline-secondary" id="btnBackupDepois">Depois</button>
                <button type="button" class="btn btn-primary-custom" id="btnBackupSim">Sim, baixar agora</button>
              </div>
            </div>
          </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modalEl = document.getElementById('modalBackup');
    const modal = new bootstrap.Modal(modalEl, { backdrop: 'static', keyboard: false });

    document.getElementById('btnBackupSim').addEventListener('click', () => {
        // Dispara o download do .db (a rota já marca o backup como feito)
        window.location.href = '/backup/download';
        modal.hide();
    });

    document.getElementById('btnBackupDepois').addEventListener('click', () => {
        // Não marca como feito — o aviso volta a aparecer na próxima vez
        // que a página for carregada, até o usuário realmente fazer o backup.
        modal.hide();
    });

    // Remove o modal do DOM depois de fechado, pra não acumular elementos
    modalEl.addEventListener('hidden.bs.modal', () => modalEl.remove());

    modal.show();
}
