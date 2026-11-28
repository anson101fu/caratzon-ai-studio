
(function(global){
  const SUPPORT_PROFILES_457 = {
    jewelry_fine_dense: { label:'珠寶幼支撐', tipMm:0.28, upperMm:0.70, midMm:0.95, baseMm:1.35, footMm:2.40, angleDeg:32, density:0.78, maxUpperMm:0.90 },
    jewelry_medium: { label:'中支撐', tipMm:0.35, upperMm:0.85, midMm:1.10, baseMm:1.55, footMm:2.80, angleDeg:30, density:0.62, maxUpperMm:1.00 },
    ring_prong_safe: { label:'戒指石托安全', tipMm:0.30, upperMm:0.70, midMm:0.95, baseMm:1.40, footMm:2.60, angleDeg:38, density:0.66, maxUpperMm:0.95 },
    brooch_back_safe: { label:'胸針背面安全', tipMm:0.32, upperMm:0.80, midMm:1.00, baseMm:1.45, footMm:2.60, angleDeg:28, density:0.58, maxUpperMm:0.95 }
  };

  function defaultProfileForProduct(productType){
    switch(String(productType || '').toLowerCase()){
      case 'earring':
      case 'openwork_earring': return 'jewelry_fine_dense';
      case 'ring': return 'ring_prong_safe';
      case 'brooch': return 'brooch_back_safe';
      case 'pendant':
      default: return 'jewelry_medium';
    }
  }

  function mergeProfile(base, override){
    return Object.assign({}, base || {}, override || {});
  }

  function buildSupportSpec(opts){
    const productType = opts.productType || 'pendant';
    const style = opts.supportStyle || defaultProfileForProduct(productType);
    const base = SUPPORT_PROFILES_457[style] || SUPPORT_PROFILES_457[defaultProfileForProduct(productType)];
    const spec = mergeProfile(base, {
      productType,
      outputMode: opts.outputMode || 'combined',
      avoidHorizontalRods: true,
      backfacePriority: opts.backfacePriority !== false,
      autoRotate: opts.autoRotate !== false,
      supportsOnly: opts.outputMode === 'supports_only'
    });
    if (typeof opts.tipMm === 'number') spec.tipMm = opts.tipMm;
    if (typeof opts.upperMm === 'number') spec.upperMm = Math.min(opts.upperMm, spec.maxUpperMm || opts.upperMm);
    if (typeof opts.angleDeg === 'number') spec.angleDeg = opts.angleDeg;
    if (typeof opts.density === 'number') spec.density = opts.density;
    return spec;
  }

  function summarizeSupportIntent(spec){
    return [
      `產品類型: ${spec.productType}`,
      `支撐風格: ${spec.label || 'custom'}`,
      `輸出模式: ${spec.outputMode}`,
      `接觸點: ${spec.tipMm} mm`,
      `上段/中段/底部: ${spec.upperMm}/${spec.midMm}/${spec.baseMm} mm`,
      `底腳: ${spec.footMm} mm`,
      `角度: ${spec.angleDeg}°`,
      `密度: ${spec.density}`,
      `禁止橫向粗柱: 是`,
      `背面優先: ${spec.backfacePriority ? '是' : '否'}`
    ].join(' | ');
  }

  global.CARATZON_SUPPORT_457 = {
    SUPPORT_PROFILES_457,
    defaultProfileForProduct,
    buildSupportSpec,
    summarizeSupportIntent
  };
})(typeof window !== 'undefined' ? window : globalThis);
