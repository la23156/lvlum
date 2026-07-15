import { useFavorites } from '../favorites'

export function FavButton({ k, big = false, inline = false }: { k: string; big?: boolean; inline?: boolean }) {
  const { isFav, toggle } = useFavorites()
  const on = isFav(k)
  return (
    <button
      className={`favbtn ${on ? 'on' : ''} ${big ? 'big' : ''} ${inline ? 'inline' : ''}`}
      title={on ? 'Remove from favorites' : 'Add to favorites'}
      aria-label="favorite"
      onClick={e => { e.preventDefault(); e.stopPropagation(); toggle(k) }}
    >{on ? '♥' : '♡'}{big && <span className="lbl">{on ? 'Favorited' : 'Favorite'}</span>}</button>
  )
}
