async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });

  if (!response.ok) {
    if (response.status === 401) {
      window.location.href = '/';
      throw new Error('Login required');
    }

    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

function injectProtectedNav() {
  const nav = document.querySelector('.nav');
  if (!nav || document.body.dataset.page === 'home') {
    return;
  }

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'secondary';
  button.textContent = 'Log out';
  button.addEventListener('click', async () => {
    await api('/api/logout', { method: 'POST' });
    window.location.href = '/';
  });
  nav.appendChild(button);
}

function renderList(container, items, renderItem) {
  container.innerHTML = '';
  items.forEach((item) => container.appendChild(renderItem(item)));
}

function createListItem(title, detail, meta) {
  const element = document.createElement('article');
  element.className = 'list-item';
  element.innerHTML = `
    ${meta ? `<small>${meta}</small>` : ''}
    <strong>${title}</strong>
    <p>${detail}</p>
  `;
  return element;
}

function createMessageBubble(entry) {
  const element = document.createElement('article');
  element.className = 'message-bubble';
  element.innerHTML = `
    <span class="message-meta">${entry.author} • ${entry.timestamp}</span>
    <p>${entry.message}</p>
  `;
  return element;
}

async function redirectIfLoggedIn() {
  const session = await api('/api/session');
  if (session.authenticated) {
    window.location.href = session.home;
  }
}

function bindLogin(role) {
  const form = document.querySelector(`[data-login-form="${role}"]`);
  const error = document.querySelector(`[data-login-error="${role}"]`);
  if (!form) {
    return;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.textContent = '';

    try {
      const result = await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({
          role,
          email: form.email.value,
          password: form.password.value
        })
      });

      window.location.href = result.redirectTo;
    } catch (_error) {
      error.textContent = 'Invalid credentials. Use the demo login shown below.';
    }
  });
}

async function initEmployeePage() {
  const list = document.querySelector('#knowledge-list');
  const form = document.querySelector('#knowledge-form');

  async function refresh() {
    const entries = await api('/api/knowledge');
    renderList(list, entries, (entry) =>
      createListItem(entry.title, entry.guidance, `${entry.category} • updated ${new Date(entry.updatedAt).toLocaleDateString()}`)
    );
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const payload = {
      title: form.title.value,
      category: form.category.value,
      guidance: form.guidance.value
    };

    await api('/api/knowledge', {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    form.reset();
    refresh();
  });

  refresh();
}

async function initChatPage() {
  const chatbotStream = document.querySelector('#chatbot-stream');
  const coachStream = document.querySelector('#coach-stream');
  const chatbotForm = document.querySelector('#chatbot-form');
  const coachForm = document.querySelector('#coach-form');

  async function refresh() {
    const chats = await api('/api/chat');
    renderList(chatbotStream, chats.chatbot, createMessageBubble);
    renderList(coachStream, chats.coach, createMessageBubble);
  }

  async function submit(channel, form) {
    await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ channel, message: form.message.value })
    });

    form.reset();
    refresh();
  }

  chatbotForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit('chatbot', chatbotForm);
  });

  coachForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit('coach', coachForm);
  });

  refresh();
}

async function initHealthPage() {
  const form = document.querySelector('#health-form');
  const goalsList = document.querySelector('#goals-list');
  const analysisList = document.querySelector('#analysis-list');
  const recommendation = document.querySelector('#daily-recommendation');
  const focus = document.querySelector('#wellness-focus');
  const statSteps = document.querySelector('#steps-stat');
  const statWater = document.querySelector('#water-stat');
  const statSleep = document.querySelector('#sleep-stat');

  async function refresh() {
    const profile = await api('/api/health');

    recommendation.textContent = profile.dailyRecommendation;
    focus.textContent = profile.wellnessFocus;
    statSteps.textContent = profile.activity.steps.toLocaleString();
    statWater.textContent = `${profile.activity.waterOz} oz`;
    statSleep.textContent = `${profile.activity.sleepHours} hrs`;

    renderList(goalsList, profile.goals, (goal) => createListItem(goal, 'Tracked within your personal health plan.'));
    renderList(analysisList, profile.analysis, (entry) => createListItem('Trend insight', entry));

    form.goals.value = profile.goals.join('\n');
    form.dailyRecommendation.value = profile.dailyRecommendation;
    form.wellnessFocus.value = profile.wellnessFocus;
    form.steps.value = profile.activity.steps;
    form.waterOz.value = profile.activity.waterOz;
    form.sleepHours.value = profile.activity.sleepHours;
    form.workouts.value = profile.activity.workouts;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    await api('/api/health', {
      method: 'POST',
      body: JSON.stringify({
        goals: form.goals.value.split('\n').map((item) => item.trim()).filter(Boolean),
        dailyRecommendation: form.dailyRecommendation.value,
        wellnessFocus: form.wellnessFocus.value,
        activity: {
          steps: Number(form.steps.value),
          waterOz: Number(form.waterOz.value),
          sleepHours: Number(form.sleepHours.value),
          workouts: Number(form.workouts.value)
        }
      })
    });

    refresh();
  });

  refresh();
}

async function initMealsPage() {
  const list = document.querySelector('#meal-list');
  const totalCalories = document.querySelector('#meal-calories');
  const form = document.querySelector('#meal-form');

  async function refresh() {
    const meals = await api('/api/meals');
    const calories = meals.reduce((sum, meal) => sum + (meal.calories || 0), 0);
    totalCalories.textContent = calories.toLocaleString();

    renderList(list, meals, (meal) =>
      createListItem(meal.mealName, meal.notes || 'No notes added.', `${meal.timeOfDay} • ${meal.calories} calories`)
    );
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    await api('/api/meals', {
      method: 'POST',
      body: JSON.stringify({
        mealName: form.mealName.value,
        timeOfDay: form.timeOfDay.value,
        notes: form.notes.value,
        calories: form.calories.value
      })
    });

    form.reset();
    refresh();
  });

  refresh();
}

const page = document.body.dataset.page;

if (page === 'home') {
  redirectIfLoggedIn();
  bindLogin('customer');
  bindLogin('employee');
}

if (page !== 'home') {
  injectProtectedNav();
}

if (page === 'employee') {
  initEmployeePage();
}

if (page === 'chat') {
  initChatPage();
}

if (page === 'health') {
  initHealthPage();
}

if (page === 'meals') {
  initMealsPage();
}