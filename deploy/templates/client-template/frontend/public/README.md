# Public Assets

This folder contains the default assets for the AI-Core-Tools client template.

## Default Assets

- **`mattin-small.png`** - Default Mattin AI logo (can be replaced with your own)
- **`favicon.ico`** - Default favicon (can be replaced with your own)

## Customization

To use your own branding:

1. **Replace the logo**: Override `mattin-small.png` with your logo file
2. **Update configuration**: Modify `src/config/libraryConfig.ts` to reference your logo
3. **Replace favicon**: Override `favicon.ico` with your favicon

## Example

```typescript
// In src/config/libraryConfig.ts
export const libraryConfig: LibraryConfig = {
  logo: '/your-logo.png',  // Your custom logo
  favicon: '/your-favicon.ico',  // Your custom favicon
  headerProps: {
    logoUrl: '/your-logo.png'  // Header logo
  }
  // ... rest of config
};
```

## File Formats

- **Logo**: PNG, SVG, or JPG (recommended: PNG with transparent background)
- **Favicon**: ICO format (16x16, 32x32, 48x48 pixels)

## Notes

- All assets in this folder are served from the root path (`/`)
- The template is configured to use these assets by default
- You can add additional assets (images, fonts, etc.) to this folder as needed
