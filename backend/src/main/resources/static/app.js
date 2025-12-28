document.addEventListener('DOMContentLoaded', () => {
  const container = document.querySelector('[data-sources]');
  const addButton = document.querySelector('[data-add-source]');
  const template = document.getElementById('source-template');

  if (!container || !addButton || !template) {
    return;
  }

  const reindex = () => {
    const rows = container.querySelectorAll('[data-source-row]');
    rows.forEach((row, idx) => {
      const input = row.querySelector('input[name^="sources["]');
      if (input) {
        input.name = `sources[${idx}].url`;
      }
    });
  };

  const addRow = () => {
    const fragment = template.content.cloneNode(true);
    container.appendChild(fragment);
    reindex();
  };

  addButton.addEventListener('click', () => addRow());

  container.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.matches('[data-remove-source]')) {
      const row = target.closest('[data-source-row]');
      if (row) {
        row.remove();
        if (container.querySelectorAll('[data-source-row]').length === 0) {
          addRow();
        } else {
          reindex();
        }
      }
    }
  });

  reindex();
});

document.addEventListener('click', (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const button = target.closest('button[data-headline]');
  if (button) {
    const headline = button.dataset.headline || 'esta entrada';
    if (!confirm(`¿Eliminar: ${headline}?`)) {
      event.preventDefault();
    }
  }
});
