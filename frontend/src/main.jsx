import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { BooksProvider } from './Books'
import './App.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <BooksProvider><App /></BooksProvider>
    </BrowserRouter>
  </React.StrictMode>
)
