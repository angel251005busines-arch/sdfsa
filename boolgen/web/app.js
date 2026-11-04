/* Клиент демо-страницы: сбор параметров, запрос заданий, проверка ответа. */
const form = document.getElementById('form');
const statusBox = document.getElementById('status');
const tasksBox = document.getElementById('tasks');
let currentParams = null;

function collectParams() {
  const ops = [...form.querySelectorAll('input[type=checkbox]:checked')].map(el => el.value);
  return {
    task_type: form.task_type.value,
    operations: ops,
    variables: Number(form.variables.value),
    depth: Number(form.depth.value),
    nodes_max: 19,
    count: Number(form.count.value),
    difficulty: form.difficulty.value,
  };
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderTable(display) {
  if (!display || !display.rows || !display.rows.length) return null;
  const table = el('table');
  const head = el('tr');
  display.header.forEach(h => head.appendChild(el('th', null, h)));
  table.appendChild(head);
  display.rows.forEach(row => {
    const tr = el('tr');
    row.forEach(cell => tr.appendChild(el('td', null, String(cell))));
    table.appendChild(tr);
  });
  return table;
}

function placeholderFor(kind) {
  if (kind === 'column_mapping') return 'например: ABC';
  if (kind === 'int') return 'число';
  if (kind === 'dnf') return 'например: ¬A ∨ B ∧ C';
  return '0 или 1';
}

function renderTask(task) {
  const card = el('div', 'card');
  card.appendChild(el('p', 'prompt', task.prompt));
  const table = renderTable(task.display);
  if (table) card.appendChild(table);
  card.appendChild(el('div', 'meta',
    `сложность ${task.difficulty_score} · тип ${task.task_type} · id ${task.id}`));

  if (task.answer_kind === 'truth_table') return card;

  const row = el('div', 'row');
  const input = el('input');
  input.type = 'text';
  input.placeholder = placeholderFor(task.answer_kind);
  const button = el('button', 'ghost', 'Проверить');
  const verdict = el('span', 'verdict');

  button.addEventListener('click', async () => {
    const response = await fetch('/api/check', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task_id: task.id, params: currentParams, answer: input.value}),
    });
    const data = await response.json();
    if (data.error) {
      verdict.className = 'verdict bad';
      verdict.textContent = data.error;
      return;
    }
    verdict.className = 'verdict ' + (data.correct ? 'ok' : 'bad');
    verdict.textContent = data.correct ? 'верно' : 'неверно';
  });

  row.append(input, button, verdict);
  card.appendChild(row);
  return card;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  currentParams = collectParams();
  statusBox.className = '';
  statusBox.textContent = 'генерируем и проверяем…';
  tasksBox.innerHTML = '';
  try {
    const response = await fetch('/api/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({params: currentParams}),
    });
    const data = await response.json();
    if (data.error) {
      statusBox.className = 'error';
      statusBox.textContent = data.error;
      return;
    }
    const stats = data.stats || {};
    const rejectRate = Math.round((stats.reject_rate || 0) * 100);
    statusBox.textContent =
      `готово: ${data.tasks.length} заданий · в пуле ${stats.published || 0} проверенных ` +
      `(${rejectRate}% брака)`;
    data.tasks.forEach(task => tasksBox.appendChild(renderTask(task)));
  } catch (error) {
    statusBox.className = 'error';
    statusBox.textContent = 'ошибка сети: ' + error;
  }
});
