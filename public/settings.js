let agencies = [];
let selectedAgency = null;
let routes = [];
let stops = [];
let config = { buses: [] };

function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

const agencySearch = document.getElementById('agency-search');
const agencyDropdown = document.getElementById('agency-dropdown');
const agencyIdInput = document.getElementById('agency-id');
const agencySelected = document.getElementById('agency-selected');
const routeGroup = document.getElementById('route-group');
const routeSelect = document.getElementById('route-select');
const stopGroup = document.getElementById('stop-group');
const stopSelect = document.getElementById('stop-select');
const customizeGroup = document.getElementById('customize-group');
const busColor = document.getElementById('bus-color');
const busDesc = document.getElementById('bus-desc');
const addBtn = document.getElementById('add-btn');
const busList = document.getElementById('bus-list');
const emptyState = document.getElementById('empty-state');
const busCount = document.getElementById('bus-count');
const saveBtn = document.getElementById('save-btn');
const toast = document.getElementById('toast');

(async function init() {
    await loadConfig();
    await loadAgencies();
    renderBusList();
})();

async function loadConfig() {
    try {
        const res = await fetch('/api/config');
        config = await res.json();
        if (!Array.isArray(config.buses)) config.buses = [];
    } catch (e) {
        config = { buses: [] };
    }
}

async function loadAgencies() {
    try {
        const res = await fetch('/api/agencies');
        const data = await res.json();
        agencies = data.filter(a =>
            a.is_public && a.products && a.products.includes('realtime')
        ).sort((a, b) => a.long_name.localeCompare(b.long_name));
    } catch (e) {
        agencies = [];
    }
}

function showAgencies(filter = '') {
    const q = filter.toLowerCase().trim();
    const matches = q.length === 0
        ? agencies.slice(0, 15)
        : agencies.filter(a =>
            a.long_name.toLowerCase().includes(q) ||
            a.short_name.toLowerCase().includes(q)
        ).slice(0, 15);

    agencyDropdown.innerHTML = matches.map(a =>
        `<div class="dropdown-item" data-id="${escapeHtml(a.id)}" data-name="${escapeHtml(a.long_name)}"
          data-lat="${escapeHtml(a.position.latitude)}" data-lon="${escapeHtml(a.position.longitude)}">
      ${escapeHtml(a.long_name)}
    </div>`
    ).join('');

    if (matches.length === 0) {
        agencyDropdown.innerHTML = '<div class="dropdown-item" style="color:var(--text-dim)">No results</div>';
    }

    agencyDropdown.classList.remove('hidden');
}

agencySearch.addEventListener('focus', () => showAgencies(agencySearch.value));
agencySearch.addEventListener('input', () => showAgencies(agencySearch.value));

agencyDropdown.addEventListener('click', async (e) => {
    const item = e.target.closest('.dropdown-item');
    if (!item || !item.dataset.id) return;

    selectedAgency = {
        id: item.dataset.id,
        name: item.dataset.name,
        lat: item.dataset.lat,
        lon: item.dataset.lon
    };

    agencySearch.value = '';
    agencySelected.textContent = selectedAgency.name;
    agencyDropdown.classList.add('hidden');

    routeGroup.style.display = 'block';
    stopGroup.style.display = 'none';
    customizeGroup.style.display = 'none';
    addBtn.disabled = true;
    routeSelect.innerHTML = '<option value="">Loading routes...</option>';

    try {
        const res = await fetch(`/api/routes?agency=${selectedAgency.id}`);
        const data = await res.json();
        routes = (data.routes || []).filter(r => r.is_active);
        stops = data.stops || [];

        if (routes.length === 0) {
            routeSelect.innerHTML = '<option value="">No active routes found</option>';
            return;
        }

        routeSelect.innerHTML = '<option value="">Select a route...</option>' +
            routes.map(r => `<option value="${escapeHtml(r.id)}" data-color="${escapeHtml(r.color)}">${escapeHtml(r.long_name || r.short_name)}</option>`).join('');
    } catch (e) {
        routeSelect.innerHTML = '<option value="">Error loading routes</option>';
    }
});

document.addEventListener('click', (e) => {
    if (!e.target.closest('.form-group')) {
        agencyDropdown.classList.add('hidden');
    }
});

routeSelect.addEventListener('change', () => {
    const routeId = parseInt(routeSelect.value);
    if (!routeId) {
        stopGroup.style.display = 'none';
        customizeGroup.style.display = 'none';
        addBtn.disabled = true;
        return;
    }

    const route = routes.find(r => r.id === routeId);
    if (!route) return;

    const routeStopIds = route.stop_ids || route.stops || [];
    const routeStops = stops.filter(s => routeStopIds.includes(s.id));

    stopGroup.style.display = 'block';

    if (routeStops.length === 0) {
        stopSelect.innerHTML = '<option value="">No stops found</option>';
    } else {
        stopSelect.innerHTML = '<option value="">Select a stop...</option>' +
            routeStops.map(s => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)}</option>`).join('');
    }

    if (route.color) {
        busColor.value = '#' + route.color;
    }
    customizeGroup.style.display = 'none';
    addBtn.disabled = true;
});

stopSelect.addEventListener('change', () => {
    if (stopSelect.value) {
        customizeGroup.style.display = 'block';
        addBtn.disabled = false;
    } else {
        customizeGroup.style.display = 'none';
        addBtn.disabled = true;
    }
});

addBtn.addEventListener('click', () => {
    if (config.buses.length >= 4) {
        showToast('Maximum 4 buses allowed');
        return;
    }

    const routeId = parseInt(routeSelect.value);
    const stopId = parseInt(stopSelect.value);
    const route = routes.find(r => r.id === routeId);
    const stop = stops.find(s => s.id === stopId);

    if (!selectedAgency || !route || !stop) return;

    const bus = {
        agencyId: parseInt(selectedAgency.id),
        agencyName: selectedAgency.name,
        agencyLat: parseFloat(selectedAgency.lat),
        agencyLon: parseFloat(selectedAgency.lon),
        routeId: route.id,
        routeName: route.long_name || route.short_name,
        stopId: stop.id,
        stopName: stop.name,
        color: busColor.value,
        description: busDesc.value.trim()
    };

    config.buses.push(bus);
    renderBusList();
    resetForm();
});

function resetForm() {
    agencySearch.value = '';
    agencySelected.textContent = '';
    selectedAgency = null;
    routeGroup.style.display = 'none';
    stopGroup.style.display = 'none';
    customizeGroup.style.display = 'none';
    addBtn.disabled = true;
    busDesc.value = '';
    busColor.value = '#4A90D9';
}

function renderBusList() {
    busCount.textContent = `${config.buses.length}/4`;
    emptyState.style.display = config.buses.length === 0 ? 'block' : 'none';

    if (config.buses.length >= 4) {
        addBtn.disabled = true;
        addBtn.textContent = 'Max 4 buses';
    } else {
        addBtn.textContent = 'Add Bus';
    }

    busList.innerHTML = config.buses.map((bus, i) => `
    <div class="bus-item" draggable="true" data-index="${i}">
      <span class="grip-icon">\u283f</span>
      <span class="bus-order">${i + 1}</span>
      <span class="bus-color-dot" style="background:${escapeHtml(bus.color)}"></span>
      <div class="bus-info">
        <div class="bus-name">${escapeHtml(bus.routeName)}</div>
        <div class="bus-detail">${escapeHtml(bus.stopName)} — ${escapeHtml(bus.agencyName)}</div>
        ${bus.description ? `<div class="bus-desc-tag">${escapeHtml(bus.description)}</div>` : ''}
      </div>
      <button class="btn btn-delete" data-index="${i}">Remove</button>
    </div>
  `).join('');

    attachDragEvents();
}

busList.addEventListener('click', (e) => {
    const delBtn = e.target.closest('.btn-delete');
    if (!delBtn) return;
    const idx = parseInt(delBtn.dataset.index);
    config.buses.splice(idx, 1);
    renderBusList();
});

let dragIndex = null;

function attachDragEvents() {
    const items = busList.querySelectorAll('.bus-item');
    items.forEach(item => {
        item.addEventListener('dragstart', (e) => {
            dragIndex = parseInt(item.dataset.index);
            item.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            items.forEach(i => i.classList.remove('drag-over'));
            dragIndex = null;
        });

        item.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            item.classList.add('drag-over');
        });

        item.addEventListener('dragleave', () => {
            item.classList.remove('drag-over');
        });

        item.addEventListener('drop', (e) => {
            e.preventDefault();
            const dropIndex = parseInt(item.dataset.index);
            if (dragIndex === null || dragIndex === dropIndex) return;

            const [moved] = config.buses.splice(dragIndex, 1);
            config.buses.splice(dropIndex, 0, moved);
            renderBusList();
        });
    });
}

saveBtn.addEventListener('click', async () => {
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const data = await res.json();
        if (data.success) {
            showToast('Configuration saved');
        } else {
            showToast('Error: ' + (data.error || 'Unknown'));
        }
    } catch (e) {
        showToast('Network error saving config');
    }
});

function showToast(msg) {
    toast.textContent = msg;
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 2500);
}
