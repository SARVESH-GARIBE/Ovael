import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppShell } from '../components/AppShell';

describe('AppShell', () => {
  it('renders brand, navigation items, and honesty strip indications', () => {
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    expect(screen.getByText('OVAEL')).toBeInTheDocument();
    expect(screen.getByText('Theater')).toBeInTheDocument();
    expect(screen.getByText('Scans')).toBeInTheDocument();
    expect(screen.getByText('Submit Test Flow')).toBeInTheDocument();
    expect(screen.getByText('Review Queue')).toBeInTheDocument();
    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.getByText('Models [Admin]')).toBeInTheDocument();
    expect(screen.getByText('Web Domain')).toBeInTheDocument();
    expect(screen.getByText('coming soon')).toBeInTheDocument();
  });
});
