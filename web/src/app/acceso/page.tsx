import { Suspense } from "react";
import Formulario from "./formulario";

export default function Acceso() {
  return (
    <main className="grid min-h-dvh place-items-center p-4">
      <Suspense>
        <Formulario />
      </Suspense>
    </main>
  );
}
