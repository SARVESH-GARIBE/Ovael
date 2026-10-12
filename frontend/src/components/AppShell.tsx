import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { Boxes, ClipboardCheck, FlaskConical, Globe, KeyRound, Network } from 'lucide-react';
import { getAdminToken, setAdminToken } from '../api/client';
import { useStats } from '../api/hooks';
import { useLiveStatus } from '../api/live';

const NAV = [
  { to: '/', label: 'Network', icon: Network, end: true },
  { to: '/website', label: 'Website', icon: Globe },
  { to: '/review', label: 'Review', icon: ClipboardCheck, badge: 'reviews' as const },
  { to: '/lab', label: 'Lab', icon: FlaskConical },
  { to: '/models', label: 'Models', icon: Boxes },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#122C4F" />
        <circle cx="16" cy="16" r="8" fill="none" stroke="#FBF9E4" strokeWidth="3" />
        <circle cx="16" cy="16" r="2.5" fill="#5B88B2" />
      </svg>
      <span className="text-lg font-semibold tracking-tight">
        ovael<span className="text-ocean">.ai</span>
      </span>
    </div>
  );
}

function TokenField() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(getAdminToken());
  return (
    <div>
      <button
        className="flex items-center gap-2 text-xs text-pearl-dim hover:text-pearl"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <KeyRound className="h-3.5 w-3.5" /> Admin token {getAdminToken() ? '· set' : ''}
      </button>
      {open && (
        <input
          type="password"
          className="input mt-2 w-full py-1.5 text-xs"
          placeholder="needed for undo, review, retrain"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setAdminToken(e.target.value);
          }}
        />
      )}
    </div>
  );
}

export function AppShell() {
  const live = useLiveStatus();
  const stats = useStats(undefined, 60);
  const pending = stats.data?.pending_reviews ?? 0;

  return (
    <div className="flex min-h-screen flex-col bg-noir text-pearl md:flex-row">
      <aside className="flex shrink-0 flex-row items-center justify-between gap-4 border-b border-midnight-800 px-4 py-3 md:sticky md:top-0 md:h-screen md:w-56 md:flex-col md:items-stretch md:justify-start md:border-b-0 md:border-r md:px-5 md:py-6">
        <Logo />
        <nav className="flex gap-1 md:mt-10 md:flex-col" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end, badge }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive ? 'bg-midnight-800 text-pearl' : 'text-pearl-dim hover:text-pearl'
                }`
              }
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{label}</span>
              {badge && pending > 0 && (
                <span className="ml-auto rounded-full bg-risk-suspicious/20 px-1.5 text-[11px] font-semibold text-risk-suspicious">
                  {pending}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="hidden space-y-3 md:mt-auto md:block">
          <div className="flex items-center gap-2 text-xs text-pearl-dim">
            <span
              className={`h-2 w-2 rounded-full ${
                live === 'open'
                  ? 'bg-ocean'
                  : live === 'connecting'
                    ? 'bg-risk-medium'
                    : 'bg-risk-high'
              }`}
            />
            {live === 'open' ? 'Live' : live === 'connecting' ? 'Connecting…' : 'Backend offline'}
          </div>
          <TokenField />
        </div>
      </aside>
      <main className="min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
