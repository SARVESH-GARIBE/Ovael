import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public override state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Note: Never log sensitive data or tokens
    console.error('ErrorBoundary caught error:', error.message, errorInfo.componentStack);
  }

  public override render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-dark-950 flex items-center justify-center p-6 text-slate-100">
          <div className="max-w-md w-full bg-dark-900 border border-dark-700 rounded-xl p-8 shadow-2xl text-center">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-neon-red/10 border border-neon-red/30 text-neon-red mb-4 text-2xl font-mono">
              !
            </div>
            <h1 className="text-xl font-bold text-white mb-2 font-mono">Application Error</h1>
            <p className="text-sm text-slate-400 mb-6">
              An unexpected error occurred in the security console interface.
            </p>
            <div className="text-xs font-mono bg-dark-950 p-3 rounded border border-dark-800 text-slate-300 text-left overflow-auto max-h-32 mb-6">
              {this.state.error?.message || 'Unknown error'}
            </div>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-dark-800 hover:bg-dark-700 text-neon-cyan border border-neon-cyan/40 rounded-lg text-sm font-medium transition-colors"
            >
              Reload Interface
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
