import React from 'react';
import { Link } from 'react-router-dom';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="flex-1 flex items-center justify-center p-6 text-center">
      <div className="max-w-md w-full bg-dark-900 border border-dark-800 rounded-xl p-8">
        <div className="text-4xl font-mono text-neon-cyan font-bold mb-2">404</div>
        <h2 className="text-lg font-bold text-white mb-2">Target Node Not Found</h2>
        <p className="text-sm text-slate-400 mb-6">
          The requested console path does not correspond to an active service endpoint.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2 bg-dark-800 hover:bg-dark-700 text-neon-cyan border border-neon-cyan/40 rounded-lg text-sm font-medium transition-colors"
        >
          Return to Theater
        </Link>
      </div>
    </div>
  );
};
