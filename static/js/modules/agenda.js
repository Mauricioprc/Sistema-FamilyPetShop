/**
 * modules/agenda.js — Lógica do calendário visual do wizard de agendamento
 * Responsabilidade: renderizar o calendário, lidar com seleção de datas.
 * Depende de: Formatter
 */

const Agenda = (() => {

    const DIAS_SEMANA = ['DOM', 'SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB'];

    let _currentDate = new Date();
    let _onSelect = null; // callback(isoDateString)

    // --- Referências DOM (inicializadas em init()) ---
    let _grid, _monthDisplay, _dataInput, _dataDisplay, _horarioContainer;

    /**
     * Inicializa o módulo. Deve ser chamado após o DOM estar pronto.
     * @param {object} opts
     * @param {HTMLElement} opts.grid           - #calendar-days
     * @param {HTMLElement} opts.monthDisplay   - #current-month-year
     * @param {HTMLInputElement} opts.dataInput - #data (hidden date input)
     * @param {HTMLElement} opts.dataDisplay    - #data-selecionada-display
     * @param {HTMLElement} opts.horarioContainer - #horario-container
     * @param {Function}    opts.onSelect       - callback quando data é escolhida
     */
    function init(opts) {
        _grid             = opts.grid;
        _monthDisplay     = opts.monthDisplay;
        _dataInput        = opts.dataInput;
        _dataDisplay      = opts.dataDisplay;
        _horarioContainer = opts.horarioContainer;
        _onSelect         = opts.onSelect || null;

        document.getElementById('prev-month')
            ?.addEventListener('click', () => _navigate(-1));
        document.getElementById('next-month')
            ?.addEventListener('click', () => _navigate(1));

        render();
    }

    /** Avança ou recua mês. */
    function _navigate(delta) {
        _currentDate.setMonth(_currentDate.getMonth() + delta);
        render();
    }

    /** Limite mínimo: hoje + 2 dias (agendamento com 48h de antecedência). */
    function _minDate() {
        const d = new Date();
        d.setHours(0, 0, 0, 0);
        d.setDate(d.getDate() + 2);
        return d;
    }

    /** Renderiza o grid do mês corrente. */
    function render() {
        if (!_grid || !_monthDisplay) return;

        const year  = _currentDate.getFullYear();
        const month = _currentDate.getMonth();

        _monthDisplay.textContent = Formatter.monthYear(year, month);

        const firstDay  = new Date(year, month, 1).getDay();
        const lastDay   = new Date(year, month + 1, 0).getDate();
        const minDate   = _minDate();

        _grid.innerHTML = '';

        // Cabeçalho dos dias da semana
        DIAS_SEMANA.forEach(d => {
            const span = document.createElement('span');
            span.className = 'day-header-mockup';
            span.textContent = d;
            _grid.appendChild(span);
        });

        // Dias em branco antes do primeiro
        const prevMonthLastDay = new Date(year, month, 0).getDate();
        for (let i = 0; i < firstDay; i++) {
            const span = document.createElement('span');
            span.className = 'day-mockup disabled';
            span.textContent = prevMonthLastDay - firstDay + i + 1;
            _grid.appendChild(span);
        }

        // Dias do mês
        for (let day = 1; day <= lastDay; day++) {
            const span = document.createElement('span');
            span.className = 'day-mockup';
            span.textContent = day;

            const dateObj    = new Date(year, month, day);
            const dayOfWeek  = dateObj.getDay();
            const isoDate    = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            span.dataset.date = isoDate;

            const isDisabled = dateObj < minDate || dayOfWeek === 0;
            if (isDisabled) {
                span.classList.add('disabled');
                span.title = dayOfWeek === 0
                    ? 'Fechado aos Domingos'
                    : 'Agendamento apenas com 48h de antecedência';
            } else {
                span.addEventListener('click', _handleClick);
            }

            _grid.appendChild(span);
        }
    }

    function _handleClick(e) {
        // Remove active anterior
        _grid.querySelectorAll('.day-mockup.active')
             .forEach(d => d.classList.remove('active'));
        e.target.classList.add('active');

        const iso = e.target.dataset.date;
        if (_dataInput) _dataInput.value = iso;

        // Exibe data formatada
        if (_dataDisplay) {
            _dataDisplay.querySelector('strong').textContent = Formatter.date(iso);
            _dataDisplay.style.display = 'block';
        }

        // Mostra seletor de horário
        if (_horarioContainer) _horarioContainer.style.display = 'block';

        if (_onSelect) _onSelect(iso);
    }

    return { init, render };

})();
