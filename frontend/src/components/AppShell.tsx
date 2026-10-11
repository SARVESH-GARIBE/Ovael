import React from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  ShieldAlert,
  Activity,
  ListFilter,
  SendHorizontal,
  ClipboardCheck,
  BarChart3,
  Cpu,
  Globe,
  Radio,
} from 'lucide-react';

export const AppShell: React.FC = () => {
  const location = useLocation();

  const navItems = [
    { to: '/', label: 'Theater', icon: Activity, exact: true },
    { to: '/scans', label: 'Scans', icon: ListFilter },
    { to: '/submit', label: 'Submit Test Flow', icon: SendHorizontal },
    { to: '/reviews', label: 'Review Queue', icon: ClipboardCheck },
    { to: '/analytics', label: 'Analytics', icon: BarChart3 },
    { to: '/models', label: 'Models [Admin]', icon: Cpu },
  ];

  const isDemo = location.pathname.startsWith('/demo');

  return (
    <div className="flex h-screen bg-dark-950 text-slate-200 overflow-hidden font-sans">
      {/* Side Navigation */}
      <aside className="w-64 bg-dark-900 border-r border-dark-800 flex flex-col justify-between shrink-0 select-none">
        <div>
          {/* Logo / Brand */}
          <div className="h-16 px-6 flex items-center gap-3 border-b border-dark-800">
            <div className="w-8 h-8 rounded-lg bg-dark-850 border border-neon-cyan/50 flex items-center justify-center text-neon-cyan shadow-[0_0_12px_rgba(0,242,254,0.25)]">
              <ShieldAlert className="w-5 h-5 text-neon-cyan" />
            </div>
            <div>
              <div className="text-base font-bold tracking-wider text-white font-mono flex items-center gap-1.5">
                OVAEL
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan">
                  NET
                </span>
              </div>
              <div className="text-[10px] text-slate-400 tracking-tight">Security Intelligence</div>
            </div>
          </div>

          {/* Nav Links */}
          <nav className="p-3 space-y-1">
            <div className="px-3 py-2 text-[10px] font-mono uppercase tracking-wider text-slate-500 font-semibold">
              Operations
            </div>

            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.exact}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      isActive && !isDemo
                        ? 'bg-dark-800 text-neon-cyan border border-neon-cyan/30 shadow-[0_0_10px_rgba(0,242,254,0.1)]'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-dark-850'
                    }`
                  }
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                </NavLink>
              );
            })}

            {/* Greyed out Web domain - coming soon */}
            <div className="pt-2">
              <div
                className="flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium text-slate-600 bg-dark-900/50 border border-dark-800/40 cursor-not-allowed select-none"
                title="Web-tracker domain UI is planned for a future release"
              >
                <div className="flex items-center gap-3">
                  <Globe className="w-4 h-4 shrink-0 text-slate-600" />
                  <span>Web Domain</span>
                </div>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-dark-800 text-slate-500 border border-dark-700 font-mono">
                  coming soon
                </span>
              </div>
            </div>
          </nav>
        </div>

        {/* Bottom Nav Footer */}
        <div className="p-4 border-t border-dark-800 text-xs text-slate-400 space-y-2">
          <NavLink
            to="/demo"
            className={({ isActive }) =>
              `flex items-center justify-center gap-2 w-full py-2 px-3 rounded-lg border text-xs font-mono font-medium transition-all ${
                isActive
                  ? 'bg-neon-amber/10 border-neon-amber/50 text-neon-amber shadow-[0_0_10px_rgba(255,183,3,0.2)]'
                  : 'bg-dark-850 border-dark-700 text-slate-300 hover:bg-dark-800 hover:text-white'
              }`
            }
          >
            <Radio className="w-3.5 h-3.5 text-neon-amber animate-pulse" />
            <span>Launch Demo Mode</span>
          </NavLink>
          <div className="text-[10px] text-slate-500 text-center font-mono pt-1">
            v0.1.0-alpha • Pipeline Live
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Bar */}
        <header className="h-16 bg-dark-900/90 backdrop-blur border-b border-dark-800 px-6 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Domain:</span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-semibold bg-dark-800 text-neon-cyan border border-neon-cyan/40">
              <span className="w-1.5 h-1.5 rounded-full bg-neon-cyan animate-pulse"></span>
              Network Traffic Flows
            </span>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-xs text-slate-400 flex items-center gap-2">
              <span className="hidden sm:inline">Engine:</span>
              <span className="font-mono text-slate-300 bg-dark-850 px-2 py-0.5 rounded border border-dark-700 text-[11px]">
                Detection + Novelty
              </span>
            </div>
          </div>
        </header>

        {/* Content Body */}
        <main className="flex-1 flex flex-col min-h-0 overflow-auto relative">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
