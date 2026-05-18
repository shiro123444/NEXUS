import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Client from "./pages/Client";
import Admin from "./pages/Admin";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Client />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
    </BrowserRouter>
  );
}
