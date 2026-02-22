import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import ProcessingList from './pages/ProcessingList';
import ProcessingDetail from './pages/ProcessingDetail';
import './App.css';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/processing" replace />} />
        <Route path="/processing" element={<ProcessingList />} />
        <Route path="/processing/:processingId" element={<ProcessingDetail />} />
      </Routes>
    </BrowserRouter>
  );
}
