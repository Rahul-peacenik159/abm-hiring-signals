// Same logic as hiring_signals/analyze.py (simplified). Edit SELLER for your product.
const SELLER = {
  targetFamilies: ['revops', 'marketing', 'sales'],
  keywords: ['account-based', 'abm', 'intent data', 'hubspot', 'salesforce', 'clay'],
  competitors: ['6sense', 'demandbase', 'zoominfo'],
  recentDays: 30,
};
const FAMILIES = [
  ['revops', /revenue operations|revops|sales operations|marketing operations|gtm operations/i],
  ['security', /security|infosec|grc|compliance|privacy|identity/i],
  ['data', /\bdata\b|analytics|business intelligence|machine learning|\bai\b/i],
  ['marketing', /marketing|demand gen|growth|brand|content|communications/i],
  ['sales', /account executive|sales|business development|\bbdr\b|\bsdr\b|partnerships/i],
  ['customer_success', /customer success|account manager|support|implementation|onboarding/i],
  ['engineering', /engineer|developer|\bsre\b|devops|platform|architect/i],
];
const LEADER = /\b(chief|cto|ciso|cfo|cmo|cro|vp|vice president|head of|director)\b/i;
const strip = (h) => String(h || '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/<[^>]+>/g, ' ');
const norm = (ats, j) => ats === 'greenhouse'
  ? { id: String(j.id), title: j.title, posted: j.first_published || j.updated_at, url: j.absolute_url, text: strip(j.content) }
  : ats === 'lever'
  ? { id: j.id, title: j.text, posted: new Date(j.createdAt).toISOString(), url: j.hostedUrl, text: j.descriptionPlain || '' }
  : { id: j.id, title: j.title, posted: j.publishedAt, url: j.jobUrl, text: j.descriptionPlain || '' };
const cutoff = Date.now() - SELLER.recentDays * 864e5;
const now = new Date().toISOString();
const accounts = $('Accounts').all();
const responses = $('Fetch job board').all();
const out = [];
const sig = (domain, type, value, extra) => ({ account_domain: domain, signal_type: type, signal_value: value,
  tool_name: '', category: '', role: 'trigger', weight: 0, play: '', source: '', evidence: '', evidence_url: '',
  pack: 'hiring-signals', observed_at: now, ...extra });
accounts.forEach((acc, i) => {
  const { domain, ats } = acc.json;
  const body = (responses[i] && responses[i].json && responses[i].json.body) || {};
  const raw = ats === 'lever' ? (Array.isArray(body) ? body : []) : (body.jobs || []);
  const jobs = raw.filter((j) => j.isListed !== false).map((j) => norm(ats, j));
  for (const j of jobs) {
    const fam = (FAMILIES.find(([, rx]) => rx.test(j.title)) || ['other'])[0];
    const isNew = new Date(j.posted).getTime() >= cutoff;
    if (!isNew) continue;
    const text = (j.title + ' ' + j.text).toLowerCase();
    if (SELLER.targetFamilies.includes(fam)) {
      out.push(sig(domain, 'new_role', j.title, { category: fam, weight: 8, play: 'role_based_outreach', source: ats, evidence_url: j.url }));
      if (LEADER.test(j.title)) out.push(sig(domain, 'leadership_hire', j.title, { category: fam, weight: 25, play: 'new_leader_first_90_days', source: ats, evidence_url: j.url }));
    }
    SELLER.keywords.filter((k) => text.includes(k)).forEach((k) => out.push(sig(domain, 'keyword_in_job', k, { category: fam, weight: 12, play: 'initiative_match', source: ats, evidence: j.title, evidence_url: j.url })));
    SELLER.competitors.filter((k) => text.includes(k)).forEach((k) => out.push(sig(domain, 'competitor_in_job', k, { category: fam, role: 'competitor', weight: 20, play: 'competitive_displacement', source: ats, evidence: j.title, evidence_url: j.url })));
  }
  out.push(sig(domain, 'open_roles', String(jobs.length), { role: 'neutral', category: 'hiring', source: ats }));
});
return out.map((json) => ({ json }));
