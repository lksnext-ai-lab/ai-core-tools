export interface TitleProps {
  readonly titulo: string;
  readonly subtitulo: string;
  readonly variant?: 'titPrincipal' | 'titSecundario' | 'titTerciario';
  readonly subtitleMarginBottom?: number;
  readonly titleMarginBottom?: number;

}

const variantClasses: Record<NonNullable<TitleProps['variant']>, { heading: string; subtitle: string }> = {
  titPrincipal: {
    heading: 'text-[40px] tracking-[-0.8px]',
    subtitle: 'text-base',
  },
  titSecundario: {
    heading: 'text-[32px] tracking-[-0.64px]',
    subtitle: 'text-[15px]',
  },
  titTerciario: {
    heading: 'text-[30px]',
    subtitle: 'text-[14.5px]',
  },
};

export function Title({
  titulo,
  subtitulo,
  variant = 'titPrincipal',
  subtitleMarginBottom = 40,
  titleMarginBottom=8
}: TitleProps) {
  const classes = variantClasses[variant];

  return (
    <div className="text-ink">
      <h1
        className={`m-0 font-display text-ink dark:text-ink-dark font-normal leading-[1.1] ${classes.heading}`}
        style={{ marginBottom: titleMarginBottom }}
      >
        {titulo}
      </h1>
      <p
        className={`m-0 max-w-[560px] leading-[1.5] text-fg-secondary dark:text-fg-secondary-dark ${classes.subtitle}`}
        style={{ marginBottom: subtitleMarginBottom }}
      >
        {subtitulo}
      </p>
    </div>
  );
}

export default Title;