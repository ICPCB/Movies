import { Route, Routes } from "react-router-dom";
import Footer from "./components/Footer";
import NavBar from "./components/NavBar";
import { LibraryProvider } from "./hooks/useLibrary";
import History from "./pages/History";
import Home from "./pages/Home";
import Library from "./pages/Library";

export default function App() {
  return (
    <LibraryProvider>
      <div className="flex min-h-screen flex-col">
        <NavBar />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/library" element={<Library />} />
            <Route path="/history" element={<History />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </LibraryProvider>
  );
}
