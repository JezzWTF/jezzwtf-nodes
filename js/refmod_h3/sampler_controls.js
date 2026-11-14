// Pure visibility rules; values remain serialized while connected inputs override them.
export function samplerWidgetVisibility(node) {
    const clown = String(node.widgets?.find((w) => w.name === "sampler_name")?.value ?? "").startsWith("clown: ");
    const linked = (name) => !clown && !!node.inputs?.find((input) => input.name === name && input.link != null);
    return { sampler_name: !linked("sampler"), seed: !linked("noise"), cfg: !linked("guider"), cfg_enabled: !linked("guider") };
}
