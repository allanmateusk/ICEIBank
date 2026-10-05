const desenhos = {
  banco: <><path d="m4 8 8-5 8 5M5 10v8m7-8v8m7-8v8M3 21h18" /></>,
  resumo: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>,
  transferir: <><path d="M4 7h16m-5-5 5 5-5 5M20 17H4m5-5-5 5 5 5" /></>,
  historico: <><path d="M3 11a9 9 0 1 1 3 8M3 4v7h7m2-4v5l3 2" /></>,
  criar: <><rect x="3" y="5" width="18" height="15" rx="3" /><path d="M3 10h18m-9 3v5m-2.5-2.5h5" /></>,
  depositar: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
  sacar: <><path d="M12 15V3m-5 5 5-5 5 5M4 16v5h16v-5" /></>,
};
export default function Icone({ nome }) {
  return <svg className="icone" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{desenhos[nome] || desenhos.banco}</svg>;
}
