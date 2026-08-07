"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { clienteDeNavegador } from "@/lib/supabase/navegador";

export default function Formulario() {
  const router = useRouter();
  const parametros = useSearchParams();
  const siguiente = parametros.get("siguiente") ?? "/";

  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [error, setError] = useState("");
  const [entrando, setEntrando] = useState(false);

  async function entrar(evento: React.FormEvent) {
    evento.preventDefault();
    setError("");
    setEntrando(true);

    const supabase = clienteDeNavegador();
    const { error } = await supabase.auth.signInWithPassword({
      email: correo.trim(),
      password: contrasena,
    });

    if (error) {
      // El mensaje de Supabase viene en inglés y dice «Invalid login
      // credentials», que no ayuda a nadie del taller.
      setError("Correo o contraseña incorrectos.");
      setEntrando(false);
      return;
    }

    router.push(siguiente);
    router.refresh();
  }

  return (
    <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-xl shadow-zinc-900/5 ring-1 ring-zinc-900/5">
      <div className="mb-8 text-center">
        <p className="text-xs font-bold uppercase tracking-[0.12em] text-indigo-600">
          Elemetic
        </p>
        <h1 className="mt-1 text-2xl font-semibold">Iniciar sesión</h1>
      </div>

      <form onSubmit={entrar} className="space-y-4">
        <div>
          <label htmlFor="correo" className="mb-1 block text-sm font-medium">
            Correo
          </label>
          <input
            id="correo"
            type="email"
            autoComplete="username"
            autoCapitalize="none"
            required
            value={correo}
            onChange={(e) => setCorreo(e.target.value)}
            className="h-12 w-full rounded-lg border border-zinc-300 px-3 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
          />
        </div>

        <div>
          <label htmlFor="contrasena" className="mb-1 block text-sm font-medium">
            Contraseña
          </label>
          <input
            id="contrasena"
            type="password"
            autoComplete="current-password"
            required
            value={contrasena}
            onChange={(e) => setContrasena(e.target.value)}
            className="h-12 w-full rounded-lg border border-zinc-300 px-3 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
          />
        </div>

        {error && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={entrando}
          className="h-12 w-full rounded-lg bg-indigo-600 font-medium text-white transition hover:bg-indigo-700 disabled:opacity-60"
        >
          {entrando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
