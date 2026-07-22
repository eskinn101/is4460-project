const express = require('express');
const fs = require('fs/promises');
const path = require('path');
const crypto = require('crypto');

const app = express();
const port = process.env.PORT || 3000;
const publicDir = path.join(__dirname, 'public');
const dataFile = path.join(__dirname, 'data', 'store.json');
const sessions = new Map();
const credentials = {
  customer: {
    email: 'jordan@moderation.app',
    password: 'customer-demo'
  },
  employee: {
    email: 'coach@moderation.app',
    password: 'employee-demo'
  }
};

app.use(express.json());

function parseCookies(cookieHeader = '') {
  return cookieHeader
    .split(';')
    .map((entry) => entry.trim())
    .filter(Boolean)
    .reduce((cookies, entry) => {
      const separator = entry.indexOf('=');
      if (separator === -1) {
        return cookies;
      }

      const key = entry.slice(0, separator);
      const value = entry.slice(separator + 1);
      cookies[key] = decodeURIComponent(value);
      return cookies;
    }, {});
}

app.use((req, _res, next) => {
  const cookies = parseCookies(req.headers.cookie);
  req.session = cookies.moderationSession ? sessions.get(cookies.moderationSession) : null;
  req.sessionId = cookies.moderationSession || null;
  next();
});

app.use((req, res, next) => {
  if (req.path.endsWith('.html')) {
    return res.redirect('/');
  }

  next();
});

app.use(express.static(publicDir, { index: false }));

const pageMap = {
  '/': 'index.html',
  '/customer': 'customer.html',
  '/employee': 'employee.html',
  '/chat': 'chat.html',
  '/health': 'health.html',
  '/meals': 'meals.html'
};

const protectedPages = new Set(['/customer', '/employee', '/chat', '/health', '/meals']);

function requireLogin(req, res, next) {
  if (!req.session) {
    if (req.path.startsWith('/api/')) {
      return res.status(401).json({ error: 'Login required' });
    }

    return res.redirect('/');
  }

  next();
}

function requireEmployee(req, res, next) {
  if (!req.session) {
    return res.status(401).json({ error: 'Login required' });
  }

  if (req.session.role !== 'employee') {
    return res.status(403).json({ error: 'Employee access required' });
  }

  next();
}

async function readStore() {
  const raw = await fs.readFile(dataFile, 'utf8');
  return JSON.parse(raw);
}

async function writeStore(nextStore) {
  await fs.writeFile(dataFile, JSON.stringify(nextStore, null, 2));
}

for (const [route, page] of Object.entries(pageMap)) {
  app.get(route, (req, res, next) => {
    if (protectedPages.has(route) && !req.session) {
      return res.redirect('/');
    }

    if (route === '/employee' && req.session?.role !== 'employee') {
      return res.redirect('/customer');
    }

    res.sendFile(path.join(publicDir, page));
  });
}

app.get('/api/session', (req, res) => {
  if (!req.session) {
    return res.json({ authenticated: false });
  }

  res.json({
    authenticated: true,
    role: req.session.role,
    home: req.session.role === 'employee' ? '/employee' : '/customer'
  });
});

app.post('/api/login', (req, res) => {
  const { role, email, password } = req.body;
  const account = credentials[role];

  if (!account || account.email !== email || account.password !== password) {
    return res.status(401).json({ error: 'Invalid login details' });
  }

  const sessionId = crypto.randomUUID();
  sessions.set(sessionId, { role, email });
  res.setHeader('Set-Cookie', `moderationSession=${sessionId}; Path=/; HttpOnly; SameSite=Lax`);
  res.json({ success: true, redirectTo: role === 'employee' ? '/employee' : '/customer' });
});

app.post('/api/logout', (req, res) => {
  if (req.sessionId) {
    sessions.delete(req.sessionId);
  }

  res.setHeader('Set-Cookie', 'moderationSession=; Path=/; HttpOnly; Max-Age=0; SameSite=Lax');
  res.json({ success: true });
});

app.get('/api/knowledge', requireEmployee, async (_req, res, next) => {
  try {
    const store = await readStore();
    res.json(store.knowledgeBase);
  } catch (error) {
    next(error);
  }
});

app.post('/api/knowledge', requireEmployee, async (req, res, next) => {
  try {
    const { title, category, guidance } = req.body;
    if (!title || !category || !guidance) {
      return res.status(400).json({ error: 'title, category, and guidance are required' });
    }

    const store = await readStore();
    const entry = {
      id: Date.now().toString(),
      title,
      category,
      guidance,
      updatedAt: new Date().toISOString()
    };

    store.knowledgeBase.unshift(entry);
    await writeStore(store);
    res.status(201).json(entry);
  } catch (error) {
    next(error);
  }
});

app.get('/api/health', requireLogin, async (_req, res, next) => {
  try {
    const store = await readStore();
    res.json(store.users['demo-user']);
  } catch (error) {
    next(error);
  }
});

app.post('/api/health', requireLogin, async (req, res, next) => {
  try {
    const { goals, dailyRecommendation, wellnessFocus, activity } = req.body;
    const store = await readStore();
    const profile = store.users['demo-user'];

    profile.goals = Array.isArray(goals) ? goals : profile.goals;
    profile.dailyRecommendation = dailyRecommendation || profile.dailyRecommendation;
    profile.wellnessFocus = wellnessFocus || profile.wellnessFocus;
    profile.activity = activity || profile.activity;

    await writeStore(store);
    res.json(profile);
  } catch (error) {
    next(error);
  }
});

app.get('/api/meals', requireLogin, async (_req, res, next) => {
  try {
    const store = await readStore();
    res.json(store.users['demo-user'].meals);
  } catch (error) {
    next(error);
  }
});

app.post('/api/meals', requireLogin, async (req, res, next) => {
  try {
    const { mealName, timeOfDay, notes, calories } = req.body;
    if (!mealName || !timeOfDay) {
      return res.status(400).json({ error: 'mealName and timeOfDay are required' });
    }

    const store = await readStore();
    const meal = {
      id: Date.now().toString(),
      mealName,
      timeOfDay,
      notes: notes || '',
      calories: Number(calories) || 0
    };

    store.users['demo-user'].meals.unshift(meal);
    await writeStore(store);
    res.status(201).json(meal);
  } catch (error) {
    next(error);
  }
});

app.get('/api/chat', requireLogin, async (_req, res, next) => {
  try {
    const store = await readStore();
    res.json(store.chats);
  } catch (error) {
    next(error);
  }
});

app.post('/api/chat', requireLogin, async (req, res, next) => {
  try {
    const { channel, message } = req.body;
    if (!channel || !message) {
      return res.status(400).json({ error: 'channel and message are required' });
    }

    const store = await readStore();
    if (!store.chats[channel]) {
      return res.status(400).json({ error: 'invalid chat channel' });
    }

    const entry = {
      id: Date.now().toString(),
      author: 'You',
      message,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    const knowledgeLead = store.knowledgeBase[0];
    const automatedResponse = {
      id: `${Date.now()}-${channel}`,
      author: channel === 'coach' ? 'Coach Mira' : 'Moderation Bot',
      message:
        channel === 'coach'
          ? `Thanks for checking in. A strong next step is: ${knowledgeLead?.guidance || 'keep today simple and stay consistent.'}`
          : `Based on the latest guidance, consider this: ${knowledgeLead?.guidance || 'balance movement, nutrition, and recovery.'}`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    store.chats[channel].push(entry, automatedResponse);
    await writeStore(store);
    res.status(201).json(store.chats[channel]);
  } catch (error) {
    next(error);
  }
});

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: 'Internal server error' });
});

app.listen(port, () => {
  console.log(`Moderation is running on http://localhost:${port}`);
});