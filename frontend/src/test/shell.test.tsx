import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from '../components/AppShell';

describe('AppShell', () => {
  it('renders the brand and the four sections', () => {
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <AppShell />
        </MemoryRouter>
      </QueryClientProvider>
    );
    expect(screen.getByText('ovael')).toBeInTheDocument();
    for (const label of ['Network', 'Website', 'Review', 'Models']) {
      expect(screen.getByRole('link', { name: new RegExp(label) })).toBeInTheDocument();
    }
  });
});
