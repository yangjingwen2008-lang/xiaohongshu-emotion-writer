export function RainPrint() {
  return <svg className="rain-print" viewBox="0 0 440 350" fill="none" aria-hidden="true" focusable="false">
    <g stroke="currentColor" strokeWidth=".75">
      {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((ring) => (
        <ellipse key={ring} cx="254" cy="231" rx={17 + ring * 22} ry={7 + ring * 10} transform="rotate(-16 254 231)" opacity={1 - ring * .085} />
      ))}
      <path d="M254 40v190M165 98v59M322 72v85M366 126v30M104 133v53" opacity=".6" />
      <path d="M34 34h25m-25 0v25m372-25h-25m25 0v25M34 316h25m-25 0v-25m372 25h-25m25 0v-25" opacity=".45" />
    </g>
    <circle cx="254" cy="229" r="4" fill="var(--rain-signal, #dc553c)" />
    <circle cx="165" cy="157" r="2" fill="currentColor" />
    <circle cx="322" cy="157" r="2" fill="currentColor" />
  </svg>
}
