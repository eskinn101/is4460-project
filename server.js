const express = require('express');
const fs = require('fs/promises');
const path = require('path');
const crypto = require('crypto');

const app = express();
const port = process.env.PORT || 3000;
const publicDir = path.join(__dirname, 'public');
const dataFile = path.join(__dirname, 'data', 'store.json');

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

function hashPassword(password, salt) {
  return crypto.scryptSync(password, salt, 64).toString('hex');
}

function verifyPassword(password, user) {
  if (!user?.passwordSalt || !user?.passwordHash) {
    return false;
  }

  return crypto.timingSafeEqual(
    Buffer.from(user.passwordHash, 'hex'),
    Buffer.from(hashPassword(password, user.passwordSalt), 'hex')
  );
}

function publicUserProfile(user) {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    goals: user.goals,
    dailyRecommendation: user.dailyRecommendation,
    wellnessFocus: user.wellnessFocus,
    activity: user.activity,
    analysis: user.analysis,
    meals: user.meals
  };
}

async function getUserByEmail(store, email) {
  return Object.values(store.users).find((user) => user.email === email) || null;
}

app.use(async (req, _res, next) => {
  try {
    const cookies = parseCookies(req.headers.cookie);
    const sessionId = cookies.moderationSession || null;
    req.sessionId = sessionId;
    req.session = null;
    req.user = null;

    if (!sessionId) {
      return next();
    }

    const store = await readStore();
    const session = store.sessions?.[sessionId];
    const user = session ? store.users?.[session.userId] : null;

    if (!session || !user) {
      return next();
    }

    req.session = session;
    req.user = user;
    next();
  } catch (error) {
    next(error);
  }
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
  if (!req.user) {
    if (req.path.startsWith('/api/')) {
      return res.status(401).json({ error: 'Login required' });
    }

    return res.redirect('/');
  }

  next();
}

function requireEmployee(req, res, next) {
  if (!req.user) {
    return res.status(401).json({ error: 'Login required' });
  }

  if (req.user.role !== 'employee') {
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
    if (protectedPages.has(route) && !req.user) {
      return res.redirect('/');
    }

    if (route === '/employee' && req.user?.role !== 'employee') {
      return res.redirect('/customer');
    }

    res.sendFile(path.join(publicDir, page));
  });
}

app.get('/api/session', (req, res) => {
  if (!req.user) {
    return res.json({ authenticated: false });
  }

  res.json({
    authenticated: true,
    role: req.user.role,
    home: req.user.role === 'employee' ? '/employee' : '/customer',
    user: {
      id: req.user.id,
      name: req.user.name,
      email: req.user.email
    }
  });
});

app.post('/api/login', async (req, res, next) => {
  try {
    const { role, email, password } = req.body;
    const store = await readStore();
    const user = await getUserByEmail(store, email);

    if (!user || user.role !== role || !verifyPassword(password, user)) {
      return res.status(401).json({ error: 'Invalid login details' });
    }

    const sessionId = crypto.randomUUID();
    store.sessions[sessionId] = {
      id: sessionId,
      userId: user.id,
      role: user.role,
      createdAt: new Date().toISOString()
    };

    await writeStore(store);
    res.setHeader('Set-Cookie', `moderationSession=${sessionId}; Path=/; HttpOnly; SameSite=Lax`);
    res.json({ success: true, redirectTo: user.role === 'employee' ? '/employee' : '/customer' });
  } catch (error) {
    next(error);
  }
});

app.post('/api/logout', async (req, res, next) => {
  try {
    if (req.sessionId) {
      const store = await readStore();
      delete store.sessions[req.sessionId];
      await writeStore(store);
    }

    res.setHeader('Set-Cookie', 'moderationSession=; Path=/; HttpOnly; Max-Age=0; SameSite=Lax');
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
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
    const profile = store.users[_req.user.id];
    res.json(publicUserProfile(profile));
  } catch (error) {
    next(error);
  }
});

app.post('/api/health', requireLogin, async (req, res, next) => {
  try {
    const { goals, dailyRecommendation, wellnessFocus, activity } = req.body;
    const store = await readStore();
    const profile = store.users[req.user.id];

    profile.goals = Array.isArray(goals) ? goals : profile.goals;
    profile.dailyRecommendation = dailyRecommendation || profile.dailyRecommendation;
    profile.wellnessFocus = wellnessFocus || profile.wellnessFocus;
    profile.activity = activity || profile.activity;

    await writeStore(store);
    res.json(publicUserProfile(profile));
  } catch (error) {
    next(error);
  }
});

app.get('/api/meals', requireLogin, async (_req, res, next) => {
  try {
    const store = await readStore();
    res.json(store.users[_req.user.id].meals);
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

    store.users[req.user.id].meals.unshift(meal);
    await writeStore(store);
    res.status(201).json(meal);
  } catch (error) {
    next(error);
  }
});

app.get('/api/chat', requireLogin, async (_req, res, next) => {
  try {
    const store = await readStore();
    res.json(store.users[_req.user.id].chats);
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
    const user = store.users[req.user.id];
    if (!user.chats[channel]) {
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

    user.chats[channel].push(entry, automatedResponse);
    await writeStore(store);
    res.status(201).json(user.chats[channel]);
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