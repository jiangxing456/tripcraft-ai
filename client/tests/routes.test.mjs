import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const requirePackage = createRequire(import.meta.url);
const directory = path.dirname(fileURLToPath(import.meta.url));

function load(file, { user = 'owner', prisma = {}, trips = {} } = {}) {
  const loaded = { exports: {} };
  const code = ts.transpileModule(fs.readFileSync(path.join(directory, '..', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const dependencies = {
    '@/lib/auth': { auth: { api: { getSession: async () => user ? { user: { id: user } } : null } } },
    '@/lib/prisma': { prisma }, '@/lib/trips': trips,
  };
  vm.runInNewContext(code, { module: loaded, exports: loaded.exports, console, Request, Response,
    process, fetch, require: name => dependencies[name] || requirePackage(name) });
  return loaded.exports;
}

test('行程列表未登录时不查询数据库', async () => {
  const route = load('app/api/plans/route.ts', { user: null });
  assert.equal((await route.GET(new Request('http://localhost'))).status, 401);
});

test('列表和详情只查询当前用户', async () => {
  let where;
  const prisma = { tripPlan: { findMany: async query => { where = query.where; return []; } } };
  await load('app/api/plans/route.ts', { prisma }).GET(new Request('http://localhost'));
  assert.equal(where.userId, 'owner');
  prisma.tripPlan.findFirst = async query => { where = query.where; return null; };
  const route = load('app/api/plans/[id]/route.ts', { prisma });
  const response = await route.GET(new Request('http://localhost'), { params: Promise.resolve({ id: 'other-trip' }) });
  assert.equal(response.status, 404);
  assert.equal(where.id, 'other-trip');
  assert.equal(where.userId, 'owner');
});

test('删除按用户和行程共同限定，不能删除别人的行程', async () => {
  let where;
  const prisma = { tripPlan: { deleteMany: async query => { where = query.where; return { count: 0 }; } } };
  const response = await load('app/api/plans/[id]/route.ts', { prisma }).DELETE(
    new Request('http://localhost'), { params: Promise.resolve({ id: 'other-trip' }) });
  assert.equal(response.status, 404);
  assert.equal(where.userId, 'owner');
});

test('提交忽略伪造 userId，日期和预算经过校验', async () => {
  const { tripForm } = load('lib/trips.ts');
  let saved;
  const prisma = { tripPlan: { create: async query => { saved = query.data; return { id: 'trip', ...saved }; } } };
  const route = load('app/api/plan/submit/route.ts', { prisma, trips: { tripForm, triggerPlan: async () => ({ success: true }) } });
  const body = { name: '旅行', destination: '成都', startingLocation: '北京',
    duration: 3, budget: 3000, travelDates: { start: '2026-10-28' }, userId: 'victim' };
  const response = await route.POST(new Request('http://localhost', { method: 'POST', body: JSON.stringify(body) }));
  assert.equal(response.status, 200);
  assert.equal(saved.userId, 'owner');
  assert.equal(tripForm.safeParse({ ...body, budget: -1 }).success, false);
});

test('进行中的行程不能重复重试', async () => {
  const prisma = { tripPlan: { findFirst: async () => ({ status: { status: 'processing' } }) } };
  const response = await load('app/api/plans/[id]/retry/route.ts', { prisma }).POST(
    new Request('http://localhost'), { params: Promise.resolve({ id: 'trip' }) });
  assert.equal(response.status, 409);
});
