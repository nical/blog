Title: GUIs on the GPU
Date: 2021-8-10
Category: rust
Slug: gui-gpu-notes
Authors: Nical
Status: draft

# Design pillars

## Common shapes

First things first, let's look at what a typical UI renderer does most. I cannot speak to all renderers, of course, but in gneneral it tends to be all about drawing rectangles, or things that can be simplified into rectangles. It's good because rectangles are easy to reason about. Better even, these rectangles are usually axis-aligned.
A typical example is rounded rectangles which are all over web pages: If you think of the shape as a whole it is not a trivial one, but after splitting away the rounded corners, you are left with basic rectangular shapes and for the corners, quarter circles (or ellipses) that can be boxed into their own rectangles. Each corner can be drawn using a mask that is very to generate in a fragment shader.

## Common patterns

Common shapes can decomposed into rectangles with potentially simple masks, but what do we usually fill them with? Solid colors, gradients, images come to mind, or some completely custom shader. All of them have in common that they can be expressed as images. The point here is that if it helps the overall architecture, we can bake any pattern into a texture in a prior pass and render it into the scene "as an image" or in other words, via a simple texture sample.

To sum it up, if a 2D renderer is very good at rendering many axis-aligned rectangles with a simple image pattern and optionally an mask, then it can go a long way. 

I know, Most 2D UI renderers can do more than that (complex transforms, fancy blending equations, filters, etc.) But at this stage we are only looking at what the system will spend 80% of it's time doing, optimize for these first and add the rest later.


## Common bottlenecks

It is a bit unfair, because I haven't gotten to how to render things, yet I am already pin pointing the most likely bottlenecks. Bear with me though, these are common enough that they tend to apply to most GPU rendering in general. They influence a lot of early decisions.

 - Driver overhead is in my humble opinion the most common one, especially when you have to support the older APIs like OpenGL and D3D11. Not all draw calls cost the same, but as a rule of thumb, doing as much as possible with few draw calls helps performance a great deal.
 - CPU-to-GPU Data transfer (texture uploads in particular) is also a common source of performance headaches, again amplified by the old APIs. It can be spectacularly slow so I wouldn't shy away from having four different code paths tuned for the different capabilities and bugs of the various platforms, just to upload textures.
 - On the GPU side, reducing overdraw is a good place to look for significant performance improvements. Blending is not cheap, memory bandwidth is limited and screens tend to have a lot of pixels these days. Per-pixel costs scale up quickly so as much possible we should avoid the cost of rendering something that is covered by something else in front of it.

# Drawing quads

We established that we would be drawing a lot of quads. On a gpu it's quite easy to draw them with two triangles. I don't think that it is the fastest way anymore. I suspect that one can do better with compute shaders, atomics and subgroup operations, but triangles just work everywhere so it makes them very compelling for renderers that target a variety of hardware. Here I'll focus on the triangles approach.

One way to batch a lot of quads in few draw calls is to have a simple unit quad mesh and that is drawn using instancing. The parameters of the quad can go into a vertex buffer with instance step mode, it's nice and simple. It's known to not be the most efficient as far as vertex shading goes. If I remember correctly most (all?) GPUs won't put separate instances in the same wavefront and 4 vertices will hardly occupy full wavefront. In practice it isn't too bad because there's a good chance that we aren't spending that much time in the vertex shader (the number of vertices being typically small in comparison with the number of pixels to shader). If vertex shaders show up too much in profiles, it's possible to generate a mesh of, say, 16 quads with a quad index in the vertex attributes, then compute the real instance ID with something along the lines of `int instance_index = vertex.index + quads_per_instance * gl_InstanceID;`, and read the instance data from an SSBO instead of a vertex buffer. Doing this you are trading vertex streaming efficiency (on some hardware, for example AMD hardware shouldn't be penalized) to get better occupancy/parallelism. For what it's worth, WebRender just uses a single quad per instance. It works well enough and bottlenecks are elsewhere.

# Caching

Transferring Data to the GPU is not cheap, and re-drawing things that haven't changed is wasteful in GPU time, power usage and heat (heat is mostly a concern on mobile devices). At some point one has to decide if there is some caching involved and at what level. It could be caching the rendered pixels, or retaining some or all of the scene description on the GPU and a bunch of other things.
When considering this, note that:
 - If you are doing a good job of retaining rendered pixels, then retaining the drawing parameters may not be very useful as most likely they won't be used until they change which causes the retained pixels to be invalidated. Managing a cache has a cost.
 - Split your retained GPU data into groups of expected update frequency maybe the most frequently updated data doesn't need to be retained at all, in any case grouping makes it easier to group data transfers and avoid scattered updates.
 - Even within a single buffer, I like to group things if I can guess their update frequencies. For example I'll push matrices that are likely static at the start of the buffer and the animated ones at the end. Or split the buffer into large-ish chunks, some of which containing only static data and others containing only animated data, etc.

WebRender started with a "redraw everything every frame" mindset and gradually ended up caching more and more of the rendered content. The reality is that even if you are fast enough to render everything, rendering only a small portion of the window has a huge impact on power usage and that's important for a browser. As a result WebRender has caches at all levels, from rendered pixels to the scene representation on the GPU and pays a cost to manage all of that. I am not convinced that all of it is as useful as it was anymore on average. It's not a big deal, it's just a bit of technical debt and overhead that I would be mindful of if I was to start over.

That said how much is expected to be animating vs static is different in a typical web page, a desktop app and an in-game UI so you have to understand your workload and hopefully pick the simplest compromise that gives you good performance.

## GPU Data representation

WebRender does the following (for reference, may or may not be what's right for another renderer):

- For most draw calls, the instance data is a simple ivec4 which packs a bunch of 32bits and 16 bits offsets and flags (primitive ID, transform ID, source pattern ID, source mask ID, etc.). The instance buffer is generated every frame during batching. The vertex shader uses these to fetch all of the required data in various buffers. The ugly truth is that to maximize support within the sad mobile ecosystem, these buffers aren't actually buffers, they are float and integer textures, but there's some glue code that hides that well and probably a game engine wouldn't need this level of compatibility.
- Rectangles are typically stored in one of these "buffers" in world space and transformed in the vertex shader. In general most drawing parameters are in word space. For example if we are drawing an image we'll have a rectangle in world space representing the bounds of the quad we are rendering, another rectangle in world space representing where the corners of the full image would be (not necessarily the same thing, we may not be showing the whole image) and another rectangle, this one in texture space, containing the texture coordinates of the source image in a texture atlas. The first two don't need to be stored separately (they could always be equal) but they are represented in the vertex shader. Applying a clip rectangle is as simple as modifying the first rectangle, while the other two rectangles are used to compute the texture coordinates of the source image (I hope this makes sense).

There is a notable exception for text: glyphs are packed to have as little per-quad data as possible because web pages typically have a lot of text. So we'll only store a glyph offset and derive the quad size from the texture atlas info with a global scaling factor (that's a bit specific but the point is some things are in large number and deserve their specific optimizations).

It's useful to have a common instance representation (the ivec4) for different shaders. It will make batching easier to write.

# Batching

One of the most performance-sensitive parts in WebRender, and I dare say it generalizes to a lot of rendering engines. It takes a lot of effort to not be simply CPU-bound and have our main bottleneck be submitting draw calls (modern APIs make this less dramatic but it's still very much key to good performance). In WebRender my rule of thumb is "If we need more than 100 draw calls this probably going to stutter on some mobile device or low end intel GPU". a typical frame will render more than 20k quads. 100 is a harsh target and depending on what platform you plan to support you may get away with an order of magnitude more, but there is much CPU time to be saved there either way which would be better spent in other areas.

3D rendering engines tend to mostly deal with opaque content, which can be rendered correctly in any order with a z-buffer. In 2D it tends to be the opposite: lots of content with alpha blending (or some other type of blending), which need to be drawn in a specific order. That's a pretty important constraint when grouping drawing primitives into batches.

In general it helps to have few shaders that can express many types of rendering primitives. For example maybe you don't need sub-pixel AA and can use the same shader for image and text. Maybe you can pre-render gradients in a texture atlas and use the same image shader for those as well when rendering in the main scene.

Ideally you end up with very few shaders that draw into the main scene to make batching easier, and have as many specialized shaders as you want pre-rendering patterns in texture atlases.

The general idea for batching algorithms is to iterate over the primitives in back-to-front order and find a compatible batch. Compatibility is evaluated by comparing "batch keys" that contain the shader ID, blending parameters and input texture/buffer IDs (assuming you can't use bindless resources), etc.

The simplest algorithm would look like:

```Rust
for prim in back_to_front_list {
    if !prim.batch_key().is_compatible_with(current_batch.key()) {
        current_batch = make_new_batch(prim.key());
    }

    current_batch.add(prim);
}
```

It's quite simple and only tries to batch consecutive similar primitives. The nightmare scenario here is having alternating incompatible primitives. For WebRender this would definitely not provide a good enough batching so we do something that involves walking back the list of batches until we either find a compatible one (in which case we add the primitive to it), or an incompatible one that intersects with the primitive in screen space (in which case we have to create a new batch).

Something like:

```Rust
'prim_loop: for prim in back_to_front_list {
    for batch in batches.iter_mut().rev() {
        if prim.batch_key().is_compatible_with(batch.key()) {
            batch.add(prim);
            continue 'prim_loop;
        }

        if prim.overlaps(batch) {
            // Can't walk further down the batch list, it would break ordering 
            break;
        }
    }

    batches.push(make_new_batch(prim.key()));
    batches.last().add(prim);
}
```

"overlap" here could be an AABB intersection check with each primitive in the batch or a single intersection check with a batch-wide AABB. WebRender does a mix of the two where it will consider only the batch AABB if it is a good enough approximation and only track multiple AABBs per batch if a single one isn't good enough.

This is a simple and generic version of what WebRender's batching algorithm: https://github.com/nical/misc/blob/master/batching/src/ordered.rs#L70

Note that to do these AABB check we need AABBs in the same space. In WebRender we pay the cost of computing screen-space AABBs for all primitives. We amortize it by using it in various things including batching but one could decide to not pay that cost at all. You'd have to automatically consider two AABBs under different transforms as potentially overlapping and alternating transforms would generate more draw calls. Depending on the workload it may or may not be reasonable.

Having a single or few shaders that renders into the scene can lead to packing a lot of features into it and slow it down. One way to mitigate that is to have different variations of these shaders with some features turned off like masking, or repreated patterns. During batching, keep track of the set of features that are required by the primitives of each batch and select a shader variation that has as few features as possible while still having all of the requested ones. That's a good way to express that you would want to avoid using a heavier shader but would not split batches over that. Or something more involved, like would only split batches over it if it affects a certain amount of pixels. WebRender has a system like that.

# Clipping

I already mentioned that with axis-aligned rectangles, clipping can be very cheap: just move the vertices in the vertex shader. If the clip or the rectangle is not axis-aligned, the fragment shader can compute the clip and write it into the alpha channel. If that's uncommon maybe just treat this case as "general clipping". The general case for clipping can be handled by generating a mask in a texture atlas. Generalizing clips as masks helps with keeping the amount of shaders low for better batching.

## Note about grouped clips with anti-aliasing

WIth most AA techniques (the ones that are not based on some form of super-sampling), applying a clip to a group of primitive is not equivalent to applying the clip to each primitive in the group individually. It's similar to blurring a group of primitive vs blurring all primitives but less obvious so I wanted to mention it. To apply an anti-aliased clip to a group of primitive correctly you generally have to first render the group of primitive and then clip it.


# Occlusion culling

Another very important topic.

Once CPU driver overhead is dealt with, the typical next bottleneck one runs into is memory bandwidth and fill rate. Blending is not cheap. If most rendered pixels need blending then there isn't much we can do with a renderer that is based on triangle rasterization.
Usually, though, there tends to be a lot of overlapping opaque or partially content that we can take advantage of (definitely true for web pages and desktop UIs) it can have a big performance impact.

## Using the depth buffer

If there is enough opaque content it may be worth using the depth buffer. It works very well in WebRender. Opaque primitives are rendered sort of front-to-back with z read and write enabled, and then blended primitives are rendered.
A very nice aspect of moving content to the opaque pass is that batching is not constrained by painting order so it is likely to generate much less draw calls than content in the blended pass.

It pays off to split partially opaque primitives like a rounded-rectangle into the opaque parts and the ones that need blending (the corners).

## Other culling approaches

If you can't use the depth buffer for some reason or the workload is such that it is not a big win, it might still be worth keeping a list of large rectangle occluders and see if it can be used to split out parts of partially occluded primitives. Splitting axis-aligned rectangles is easy. If the occluder is not in the same space or the occludee is not a rectangle, then we can still discard fully occluded elements, although it tends to be less common in 2D than in 3D.

WebRender renders web content into layers and those layers are composited into the window or the screen. The compositing phase is either done by the window manager or by WebRender if the platform doesn't provide APIs to do that. WebRender uses the z-buffer to render into the layers but not in the compositing step. Since compositing only deals with a small number of rectangular axis-aligned layers, it is faster to split out the occluded parts on the CPU. The code for that is here: https://searchfox.org/mozilla-central/rev/0fec57c05d3996cc00c55a66f20dd5793a9bfb5d/gfx/wr/webrender/src/rectangle_occlusion.rs#5 I expect that a window manager would typically do something similar.

# What of more complex shapes?

As mentioned earlier, a lot of things that aren't rectangles can be pre-rendered separately and treated as a rectangle. Sometimes that's quite wasteful because we can determine somehow that big parts of the complex shape's AABB are empty. It can help to split it into a regular grid so that only the interesting parts of the grid are pre-rendered and later then put into the scene saving a bunch of memory and overdraw. If multiple shapes in the same space are split into the same grid, it can be useful to note the fully opaque cells and simply discard cells underneith (Another very useful occlusion culling trick). What space to pick? it could be local space or screen space depending on how often the shape change and the tile decomposition should happen.

There is a whole family of advanced rendering techniques based on regular grids. That's the basic block that pathfinder and piet-gpu are built on. I won't get into it here because I'm not trying to write a whole book, but it's a fascinating area to explore (especially when one has access to compute shaders). Reach out if you are interested.

## What about tessellating shapes (lyon, libtess2, etc.)?

Tessellation is nice in that it is very easy to integrate into a GPU renderer, and doesn't require any fancy GPU feature. Lyon is quite fast for a tessellator: it takes 3.2ms to tessellate the ghostscript tiger https://commons.wikimedia.org/wiki/File:Ghostscript_Tiger.svg with tolerance 0.2, producing 13986 vertices and 40479 indices on my laptop. It's not free but something one can consider doing every frame if need be. The tiger is a fairly complex model.

The main disadvantage of tessellation is that it is very hard to do high quality anti-aliasing. The easiest way is to use MSAA, but MSAA is hardly "high quality" (from the point of view of someone working on a web browser anyway), and quite slow on intel hardware.

It's also a rather CPU-heavy thing which can be a hard sell if you are already CPU-bound. To this date nobody has figured out a way to tesselate SVG paths efficiently on the GPU. On the other hand other approaches like piet-gpu can render them on the GPU with close to no pre-processing on the CPU (at the cost of fancy algorithms and GPU features). In the context of a game, vector graphics can be pre-processed so ther might not be a need to tessellate while the game is running.

Still, it's a handy tool. My recommendation to anyone using tessellated geometry is to not treat each shape separately (avoid a draw-call per shape!) and instead batch as much of the geometry as possible in few draw calls with enough information for the shaders to position and shade each part correctly. The trick of rendering all opaque triangles first front-to-back and then the blended ones back-to-front tends to work well for this type of content.
Another recommendation is to compress the per-vertex data as much as possible. For example store 2D coordinates as pairs of u16, normalized to the 0..1 range and then scaled to the bounding box of the drawing. If the drawing is large, split it up until u16 offers enough precision.
