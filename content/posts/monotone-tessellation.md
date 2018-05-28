Title: Tessellation using monotone decomposition
Date: 2018-2-05
Category: lyon, rust
Slug: monotone-tessellation
Authors: Nical

I introduced the concept tessellation (also called triangulation) in my [previous post](https://nical.github.io/posts/lyon-intro.html). Tessellating a path means taking a description of its contour and figuring out triangle mesh that exactly describes its interrior. I am interested in generating triangles because they can very easily and very efficiently be rendered by any graphics card. How to actually render these triangles is a topic for another post, here I'll only describe how to generate the mesh.

![illustration: tessellation of a complex path]({filename}/images/lyon-logo-tessellated.png)

The kind of path we are going to work with is composed of any number of sub-paths (which can self-intersect) and these path will for now only contain line segment (no bézier curves or arc, and we'll talk about how to support these towards the end of the post).

Programmatically figuring out a correct tessellation for an arbitrary shape is tricky. We already know one of the three edges of each triangle (the one that is on the contour of the path), and the remaining two must be found so that they don't intersect any other edges/triangles.

![illustration: ovrelapping triangles with concave polygons]({filename}/images/tess-intersect-concave.svg)

This is quite simple to figure out for convex polygons, but for arbitrary polygons it's a lot harder. We can't just choose the next vertex along the path because other edges might interfere.

![illustration: convex and concave shapes]({filename}/images/tess-convex.svg)

A naive approach would be to loop over vertices, at each iteration pick a second vertex and test whether we can insert an edge between them by looping over all of the edges and see if they would intersect. The problem with this brute-force approach is obviously its explosive algorithmic complexity, causing performance to very quickly degrade with higher numbers of vertices.

# Y-monotone polygons

We saw that convex polygons are easy to tessellate, while it is quite a bit harder with arbitrary polygons. we could partition arbitrary polygons into convex ones, but figuring out this partition isn't easy either.

An [y-monotone polygon](https://en.wikipedia.org/wiki/Monotone_polygon) is a polygon that never intersects with any horizontal line more than twice. In more intuitive terms this means that at any given point on the polygon there is a left side, a right side, and no other edge in between.

![illustration: y-monotone shapes]({filename}/images/tess-y-monotone-examples.svg)

A convex polygon, for example, is at the same time x- *and* y-monotone (it is in fact monotone with resepct to any orientation, even not axis-aligned).

Tessellating a y-monotone polygon is a little more work than convex polygons but is still a lot easier than working with arbitrary shapes. The assumption that for any given y value there is no edge between the left and right side of the polygon makes it easier to insert triange edges between the left and right side.
The general idea is to go through vertices from top to bottom, maintaining a stack of vertices that we have visited but haven't connected yet.
- If the previous vertex is on the same side, see if we can form a triangle with the two previous elements in the stack of pending vertices. If we cannot, push the new vertex to the stack.
- If the previous vertex is on the other side we can add an edge between them, then go through the stack of pending vertices and connect them all to the new vertex.

This description is a little simple and hand-wavey because the details are boring and tedious to epxress in English. The [code itself](https://github.com/nical/lyon/blob/f55b1bdac8c18c233cef1b02d66c5ea0554e7329/tessellation/src/path_fill.rs#L1654-L1698) is rather simple, and I think that the best way to understand the idea is to look at the tessellation process step by step:

(TODO: illustration)

Since we can always process all vertices in the stack when changing side, the stack only ever contains vertices from the current side. When there are vertices on the stack we know that there isn't any edge from the other side between them because the previous vertex from the other side was above all vertices on the stack and the next one will be below all of these vertices (this is guaranteed by the fact that we treaverse from top to bottom and empty the stack each time we change side).

To deal with vertices on the stack there is two types of situations:
- the chain of vertices on the stack form a shape that is bent outward, in which case it is easy to insert triangles between them since we know the opposite side cannot interfere.
- the chain of vertices form a series of a shape that is bent inward, in which case we can't connect them as the resulting triangles would be outside of the polygon, but we can form triangles between them and the next vertex on the other side.

(TODO: illustration)

Now that have seen that there is a fairly simple and efficient way to tessellate a monotone polygon, we need a way to partition arbitrary shapes into monotone shapes. We need to support any kind of concave shape with holes and even self-intersection.

# Sweep line algorithms

The monotone tessellation algorithm takes a sweep line approach. Sweep lines are very common in 2D geometry algorithms because they are very good at keeping algorithmic complexity reasonable, and the way the geometry is traversed provides guarantees that are useful for the algorithm to rely on.

The simplest way to think of a sweep line algorithm is to imagine an horizontal line that moves downward through the path and stops at each vertex. Each vertex that the line stops at is an iteration of the algorithm's main loop, and I'll sometimes refer to them as events of the sweep line.

During the traversal, we keep track of all of the edges that the imaginary line intersects (let's call them *active edges*). At each iteration we will add to the active edge list any edge that start right below the current position of the sweep line and remove edges that end immediately above.

![seep line illustration]({filename}/images/sweep-line.gif)

On the animation above, you can see our imaginary sweep line traversing a shape from top to bottom. Active edges are highlighted in orange, and the edges we are about to insert in the active edge list are in blue.

Note that the algorithm we saw earlier to tessellate a monotone shape had a bit of a sweep line feel to it in the sense that we took advantage of the order of the iteration along the y axis, but we didn't need to bother with maintaining an active edge list since it's always just the left and the right side thanks to the monotonicity.

This approach provides useful properties:

- Vertices/edges are processed in an order (in our case from top to bottom) that is geometrically meaningful, a property that can be very useful for the algorithm.
- The active edges of the sweep line are "close" to each other on the y-axis, they all at any given time share a range of y.
- The opposite is also true: if two edges never share a range of y, then they are never active at the same time. This doesn't look like much but it means that we can detect all of the intersections by testing only active edges against one another which represent a lot less work than the brute-force approach of testing all edges against all other edges.
- Another way to see the previous point is that we have the guarantee that edges below cannot intersect with edges above the sweep line, and this division is key. (TODO)


