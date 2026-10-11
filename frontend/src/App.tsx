import { Route, Routes } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { NotFoundPage } from './components/NotFoundPage';
import { ModelsPage } from './pages/ModelsPage';
import { NetworkPage } from './pages/NetworkPage';
import { ReviewPage } from './pages/ReviewPage';
import { WebsitePage } from './pages/WebsitePage';

export const App: React.FC = () => (
  <Routes>
    <Route path="/" element={<AppShell />}>
      <Route index element={<NetworkPage />} />
      <Route path="website" element={<WebsitePage />} />
      <Route path="review" element={<ReviewPage />} />
      <Route path="models" element={<ModelsPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Route>
  </Routes>
);

export default App;
