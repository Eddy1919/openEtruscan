import React from 'react';

/**
 * Aldine DESIGN SYSTEM: LAYOUT PRIMITIVES
 * 
 * These components form the structural backbone of the OpenEtruscan platform.
 * They abstract the raw CSS Aldine Grammar (.aldine-) into a typed React API.
 */

interface LayoutProps extends React.HTMLAttributes<HTMLElement> {
  children?: React.ReactNode;
  className?: string;
  id?: string;
  style?: React.CSSProperties;
  as?: React.ElementType;
  padding?: 0 | 1 | 2 | 3 | 4 | 6 | 8 | 10 | 12 | 16;
  gap?: 0 | 1 | 2 | 3 | 4 | 6 | 8 | 10 | 12 | 16;
  surface?: 'canvas' | 'bone';
  border?: 'bottom' | 'right' | 'left' | 'all' | 'none' | 'top';
  align?: 'start' | 'center' | 'end' | 'baseline' | 'stretch';
  justify?: 'start' | 'center' | 'end' | 'between' | 'around' | 'evenly';
}

const getBaseClasses = ({ padding, gap, surface, border, align, justify, className = '' }: LayoutProps) => {
  const borderClass = border === 'bottom' ? 'aldine-border-b' : 
                    border === 'top' ? 'aldine-border-t' :
                    border === 'right' ? 'aldine-border-r' : 
                    border === 'left' ? 'aldine-border-l' : 
                    border === 'all' ? 'aldine-border' : '';
  
  return [
    padding !== undefined ? `aldine-p-${padding}` : '',
    gap !== undefined ? `aldine-gap-${gap}` : '',
    surface ? `aldine-bg-${surface}` : '',
    borderClass,
    align ? `aldine-items-${align}` : '',
    justify ? `aldine-justify-${justify}` : '',
    className
  ].filter(Boolean).join(' ');
};

/**
 * Stack: Vertical layout with systematic spacing
 */
export const Stack: React.FC<LayoutProps> = (props) => {
  const classes = `aldine-stack ${getBaseClasses(props)}`;
  return <div className={classes} id={props.id} style={props.style}>{props.children}</div>;
};

/**
 * Row: Horizontal layout with alignment
 */
export const Row: React.FC<LayoutProps> = (props) => {
  const classes = `aldine-row ${getBaseClasses(props)}`;
  return <div className={classes} id={props.id} style={props.style}>{props.children}</div>;
};

/**
 * Box: A generic container for surfaces and borders
 */
export const Box: React.FC<LayoutProps> = ({ as: Component = 'div', ...props }) => {
  const classes = getBaseClasses(props);
  // @ts-ignore
  return <Component className={classes} id={props.id} style={props.style}>{props.children}</Component>;
};

/**
 * Ornament: Typographic decorations (Labels, Headings)
 */
export const Ornament = {
  Label: ({ children, className = '' }: { children: React.ReactNode, className?: string }) => (
    <span className={`aldine-label ${className}`}>{children}</span>
  ),
  Heading: ({ children, className = '' }: { children: React.ReactNode, className?: string }) => (
    <h2 className={`aldine-manuscript-heading ${className}`}>{children}</h2>
  )
};

/**
 * Separator: A hairline divider
 */
export const Separator: React.FC<{ orientation?: 'horizontal' | 'vertical', className?: string }> = ({ 
  orientation = 'horizontal',
  className = ''
}) => {
  const classes = orientation === 'horizontal' 
    ? 'aldine-w-full aldine-border-b' 
    : 'aldine-h-full aldine-border-r';
    
  return <div className={`${classes} ${className}`} arialdine-hidden="true" />;
};




