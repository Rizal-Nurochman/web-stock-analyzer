import React from 'react';
import { createRoot } from 'react-dom/client';

// Font dibundel lokal agar demo tetap rapi tanpa internet.
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter-tight/500.css';
import '@fontsource/inter-tight/600.css';

import './styles/tokens.css';
import './styles/app.css';
import App from './App.jsx';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
