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
        <div className="flex min-h-screen items-center justify-center bg-noir p-6 text-pearl">
          <div className="card w-full max-w-md p-8 text-center">
            <h1 className="text-lg font-semibold">Something broke</h1>
            <p className="mt-2 text-sm text-pearl-dim">The dashboard hit an unexpected error.</p>
            <pre className="mt-4 max-h-32 overflow-auto rounded-lg bg-noir p-3 text-left font-mono text-xs text-pearl-muted">
              {this.state.error?.message || 'Unknown error'}
            </pre>
            <button onClick={() => window.location.reload()} className="btn-primary mt-6">
              Reload
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
