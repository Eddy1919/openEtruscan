const fs = require('fs');
const glob = require('glob');

glob('app/**/*.tsx', (err, files) => {
  files.forEach(file => {
    let content = fs.readFileSync(file, 'utf8');
    
    // Replace layout wrappers with primitive divs temporarily so they compile
    content = content.replace(/<(Box|Row|Stack)/g, '<div');
    content = content.replace(/<\/(Box|Row|Stack)>/g, '</div>');
    
    // Attempt to cleanse the imports
    content = content.replace(/import\s+\{([^}]*)(Box|Row|Stack)([^}]*)\}\s+from\s+["']@\/components\/folio\/Layout["'];?/g, (match) => {
      let newVars = match.replace(/import\s+\{([^}]+)\}.*/, '$1')
                         .split(',')
                         .map(v => v.trim())
                         .filter(v => v !== 'Box' && v !== 'Row' && v !== 'Stack' && v);
      if (newVars.length > 0) {
        return `import { ${newVars.join(', ')} } from "@/components/folio/Layout";`;
      }
      return '';
    });
    
    fs.writeFileSync(file, content);
  });
});
