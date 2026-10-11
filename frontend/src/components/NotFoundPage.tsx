import React from 'react';
import { Link } from 'react-router-dom';

export const NotFoundPage: React.FC = () => {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6 text-center">
      <div>
        <div className="font-mono text-5xl font-semibold text-ocean">404</div>
        <p className="mt-3 text-sm text-pearl-dim">This page does not exist.</p>
        <Link to="/" className="btn-ghost mt-6">
          Back to network
        </Link>
      </div>
    </div>
  );
};
