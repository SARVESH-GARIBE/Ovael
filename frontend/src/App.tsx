import { Routes, Route } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { NotFoundPage } from './components/NotFoundPage';
import { PlaceholderPage } from './components/PlaceholderPage';
import { DemoPage } from './theater/DemoPage';
import { TheaterContainer } from './theater/TheaterContainer';

export const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        {/* Main Theater View */}
        <Route
          index
          element={
            <TheaterContainer
              isDemo={true}
              initialEvents={[
                {
                  id: 'init-flow-1',
                  domain: 'network',
                  status: 'completed',
                  origin: 'demo',
                  is_stub: false,
                  predicted_class: 'benign',
                  confidence: 0.98,
                  is_novel: false,
                  novelty_score: 0.05,
                  risk_score: 0.0,
                  severity: 'benign',
                  flow_metadata: {
                    source_ip: '192.168.1.105',
                    destination_ip: '10.0.0.1',
                    source_port: 54321,
                    destination_port: 443,
                    protocol: 'TCP',
                  },
                  timestamp: Date.now(),
                },
              ]}
            />
          }
        />

        {/* Demo Mode Route (/demo) */}
        <Route path="demo" element={<DemoPage />} />

        {/* Placeholder Pages awaiting Backend API wiring in subsequent phases */}
        <Route
          path="scans"
          element={
            <PlaceholderPage
              title="Scans Explorer"
              description="Historical flow scans with domain filters, cursor pagination, and Theater replay."
              badge="Phase F6"
            />
          }
        />
        <Route
          path="submit"
          element={
            <PlaceholderPage
              title="Submit Network Flow"
              description="Interactive form to submit raw network flow features for real-time analysis."
              badge="Phase F6"
            />
          }
        />
        <Route
          path="reviews"
          element={
            <PlaceholderPage
              title="Analyst Review Queue"
              description="Human-in-the-loop review workflow for novel flows flagged by the novelty detector."
              badge="Phase F6"
            />
          }
        />
        <Route
          path="analytics"
          element={
            <PlaceholderPage
              title="Novelty & Detection Analytics"
              description="Novelty rate telemetry by model version over time."
              badge="Phase F6"
            />
          }
        />
        <Route
          path="models"
          element={
            <PlaceholderPage
              title="Model Inventory & Curated Export"
              description="Active and shadow model versions with stub indicators and admin export."
              badge="Phase F6 [Admin]"
            />
          }
        />

        {/* 404 Route */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
};

export default App;
