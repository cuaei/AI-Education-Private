import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import OperationFeedback from './OperationFeedback';
import './styles.css';
import './workspace.css';
import './registration.css';
import './branding.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><OperationFeedback/><App/></React.StrictMode>);
