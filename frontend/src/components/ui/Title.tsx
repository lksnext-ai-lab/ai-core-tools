import './Title.css';

export interface TitleProps {
  titulo: string;
  subtitulo: string;
}

export function Title({ titulo, subtitulo }: TitleProps) {
  return (
    <div className="ui-title">
      <h1 className="ui-title__heading">{titulo}</h1>
      <p className="ui-title__subtitle">{subtitulo}</p>
    </div>
  );
}

export default Title;